"""Routing and real native model adapter/loss checks; no Hub downloads."""
import importlib.util
import tempfile
import unittest
from architectures import training_architecture, native_support, lora_targets
from train_worker import seq2seq_text, encode_seq2seq, target_token_count


class ArchitectureTests(unittest.TestCase):
    def test_encoder_decoder_and_decoder_variants_use_distinct_loaders(self):
        for family in ('t5', 'mt5', 'bart', 'mbart', 'pegasus', 'marian'):
            self.assertEqual(training_architecture({'model_type': family}), 'seq2seq')
        self.assertEqual(training_architecture({'model_type': 'bart', 'is_encoder_decoder': False}), 'causal')
        self.assertEqual(training_architecture({'model_type': 'bart', 'architectures': ['BartForCausalLM']}), 'causal')
        self.assertEqual(training_architecture({'architectures': ['T5ForConditionalGeneration']}), 'seq2seq')
        self.assertEqual(training_architecture({'model_type': 'gpt2'}), 'causal')
        self.assertEqual(training_architecture({'is_encoder_decoder': True}, 'VLM'), 'image_text_to_text')

    def test_seq2seq_source_never_contains_the_final_answer(self):
        self.assertEqual(seq2seq_text({'instruction': 'translate', 'input': 'hello', 'output': 'bonjour'}), ('translate\nhello', 'bonjour'))
        row = {'messages': [{'role': 'system', 'content': 'translate'}, {'role': 'user', 'content': 'hello'}, {'role': 'assistant', 'content': 'bonjour'}]}
        self.assertEqual(seq2seq_text(row), ('system: translate\nuser: hello', 'bonjour'))
        with self.assertRaises(ValueError):
            seq2seq_text({'messages': [{'role': 'user', 'content': 'hello'}]})


RUNTIME = all(importlib.util.find_spec(name) for name in ('torch', 'transformers', 'peft'))


@unittest.skipUnless(RUNTIME, 'Optional training runtime is not installed')
class NativeAdapterTests(unittest.TestCase):
    def setUp(self):
        import torch
        from tokenizers import Tokenizer, models, pre_tokenizers, processors
        from transformers import PreTrainedTokenizerFast
        torch.set_num_threads(1)
        tok = Tokenizer(models.WordLevel({'<pad>': 0, '</s>': 1, '<unk>': 2, 'hello': 3, 'bonjour': 4, 'translate': 5, 'world': 6}, unk_token='<unk>'))
        tok.pre_tokenizer = pre_tokenizers.Whitespace()
        tok.post_processor = processors.TemplateProcessing(single='$A </s>', special_tokens=[('</s>', 1)])
        self.tokenizer = PreTrainedTokenizerFast(tokenizer_object=tok, pad_token='<pad>', eos_token='</s>', unk_token='<unk>')
        self.rows = [{'instruction': 'translate hello', 'output': 'bonjour'}, {'instruction': 'hello', 'output': 'bonjour world'}]

    def test_separate_labels_padding_limits_and_unshifted_token_counts(self):
        batch = encode_seq2seq(self.tokenizer, self.rows, 16)
        self.assertEqual(batch['input_ids'][0].tolist(), [5, 3, 1])
        self.assertEqual(batch['labels'][0].tolist(), [4, 1, -100])
        self.assertEqual(target_token_count(batch['labels'], 'seq2seq'), 5)
        self.assertEqual(target_token_count(batch['labels'], 'causal'), 3)
        self.assertNotIn('token_type_ids', batch)
        prompt = encode_seq2seq(self.tokenizer, self.rows, 16, prompt_only=True)
        self.assertNotIn('labels', prompt)
        with self.assertRaisesRegex(ValueError, 'Encoder input'):
            encode_seq2seq(self.tokenizer, self.rows, 2)
        with self.assertRaisesRegex(ValueError, 'Decoder answer'):
            encode_seq2seq(self.tokenizer, [{'instruction': 'hello', 'output': 'bonjour world world'}], 3)

    def test_t5_and_bart_native_loss_gradients_adapter_reload_and_generation(self):
        import torch
        from transformers import T5Config, T5ForConditionalGeneration, BartConfig, BartForConditionalGeneration
        from peft import LoraConfig, get_peft_model, PeftModel
        configs = [T5Config(vocab_size=7, d_model=16, d_ff=32, num_layers=1, num_decoder_layers=1, num_heads=2, d_kv=8, decoder_start_token_id=0, pad_token_id=0, eos_token_id=1),
                   BartConfig(vocab_size=7, d_model=16, encoder_layers=1, decoder_layers=1, encoder_attention_heads=2, decoder_attention_heads=2, encoder_ffn_dim=32, decoder_ffn_dim=32, decoder_start_token_id=1, pad_token_id=0, eos_token_id=1, max_position_embeddings=32)]
        for cfg, cls, expected in zip(configs, [T5ForConditionalGeneration, BartForConditionalGeneration], [['q', 'v'], ['q_proj', 'v_proj']]):
            with self.subTest(family=cfg.model_type):
                self.assertTrue(native_support(cfg.to_dict(), 'LLM'))
                base = cls(cfg)
                targets = lora_targets(base, 'seq2seq')
                self.assertEqual(targets, expected)
                model = get_peft_model(base, LoraConfig(r=2, lora_alpha=4, target_modules=targets, task_type='SEQ_2_SEQ_LM'))
                model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False})
                model.enable_input_require_grads();model.config.use_cache=False
                batch = encode_seq2seq(self.tokenizer, self.rows, 16)
                model.train();loss = model(**batch).loss
                self.assertTrue(torch.isfinite(loss));loss.backward()
                self.assertTrue(any(p.grad is not None and bool(p.grad.abs().sum()) for p in model.parameters() if p.requires_grad))
                # The labels include both the first answer token and EOS, without causal shifting.
                torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=.001).step()
                model.eval()
                with tempfile.TemporaryDirectory() as directory:
                    model.save_pretrained(directory, safe_serialization=True)
                    restored = PeftModel.from_pretrained(cls(cfg), directory, is_trainable=True, local_files_only=True)
                    self.assertEqual(restored.peft_config['default'].task_type, 'SEQ_2_SEQ_LM')
                    restored.eval()
                    result = restored.generate(**encode_seq2seq(self.tokenizer, self.rows, 16, prompt_only=True), max_new_tokens=3, do_sample=False)
                    self.assertEqual(result.shape[0], 2)
                    self.assertLessEqual(result.shape[1], 4)

    def test_gpt2_fused_projection_adapters_and_unknown_architecture(self):
        from transformers import GPT2Config, GPT2LMHeadModel
        from peft import LoraConfig, get_peft_model
        import torch
        cfg = GPT2Config(vocab_size=7, n_embd=16, n_layer=1, n_head=2, n_positions=32)
        base = GPT2LMHeadModel(cfg)
        self.assertEqual(lora_targets(base, 'causal'), 'all-linear')
        model = get_peft_model(base, LoraConfig(r=2, lora_alpha=4, target_modules='all-linear', task_type='CAUSAL_LM'))
        inputs = torch.tensor([[3, 4, 1]])
        loss = model(input_ids=inputs, labels=inputs).loss
        loss.backward();self.assertTrue(torch.isfinite(loss))
        self.assertTrue(native_support(cfg.to_dict(), 'LLM'))
        self.assertFalse(native_support({'model_type': 'requires_external_custom_code'}, 'LLM'))


if __name__ == '__main__':
    unittest.main()

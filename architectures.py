"""Shared native Transformers routing for catalog, preflight and CUDA worker."""
from __future__ import annotations


def training_architecture(config, kind='LLM'):
    if kind == 'VLM':
        return 'image_text_to_text'
    names = config.get('architectures') or []
    if config.get('is_encoder_decoder') is True:
        return 'seq2seq'
    if config.get('is_encoder_decoder') is False or any(str(n).endswith(('ForCausalLM', 'LMHeadModel')) for n in names):
        return 'causal'
    if any(str(n).endswith(('ForConditionalGeneration', 'ForSeq2SeqLM')) for n in names):
        return 'seq2seq'
    # Hub summaries often omit is_encoder_decoder and architectures.
    if config.get('model_type') in {'t5', 'mt5', 'longt5', 'umt5', 'bart', 'mbart', 'marian', 'pegasus', 'pegasus_x', 'm2m_100', 'nllb-moe', 'switch_transformers', 'bigbird_pegasus', 'blenderbot', 'blenderbot-small', 'fsmt', 'led'}:
        return 'seq2seq'
    return 'causal'


def native_support(config, kind):
    """Return None when Transformers is absent (e.g. offline preview/stdlib CI)."""
    family = config.get('model_type')
    if not family:
        return None
    try:
        from transformers.models.auto.modeling_auto import (
            MODEL_FOR_CAUSAL_LM_MAPPING_NAMES, MODEL_FOR_SEQ_TO_SEQ_CAUSAL_LM_MAPPING_NAMES,
            MODEL_FOR_IMAGE_TEXT_TO_TEXT_MAPPING_NAMES,
        )
    except ImportError:
        return None
    mapping = {'causal': MODEL_FOR_CAUSAL_LM_MAPPING_NAMES,
               'seq2seq': MODEL_FOR_SEQ_TO_SEQ_CAUSAL_LM_MAPPING_NAMES,
               'image_text_to_text': MODEL_FOR_IMAGE_TEXT_TO_TEXT_MAPPING_NAMES}
    return family in mapping[training_architecture(config, kind)]


def lora_targets(model, architecture):
    names = {name.rsplit('.', 1)[-1] for name, _ in model.named_modules()}
    # T5 uses q/v in both encoder self-attention and decoder cross-attention.
    pairs = (('q', 'v'), ('q_proj', 'v_proj')) if architecture == 'seq2seq' else (('q_proj', 'v_proj'),)
    for pair in pairs:
        if set(pair) <= names:
            return list(pair)
    # Includes GPT-2's fused Conv1D projections; PEFT excludes the output head.
    return 'all-linear'

from unittest.mock import patch,MagicMock
import test_training_api as training_api

class HubAPITests(training_api.TrainingAPITests):
    def test_catalog_and_account_routes_require_login(self):
        for path in ['/api/huggingface/account','/api/huggingface/models','/api/huggingface/model?id=example/model','/api/huggingface/avatar?author=example','/api/huggingface/download']:
            self.assertEqual(self.request(path,auth=False)[0],401)
    def test_account_connect_requires_csrf_and_does_not_echo_token(self):
        token='hf_SyntheticReadTokenForAPITesting123'
        with patch.object(self.server.huggingface,'_request',return_value=({'name':'example'},'')) as request:
            self.assertEqual(self.request('/api/huggingface/connect',{'token':token},csrf=False)[0],403)
            request.assert_not_called()
            status,body=self.request('/api/huggingface/connect',{'token':token})
        self.assertEqual(status,200);self.assertNotIn(token,str(body))
        self.assertEqual(self.request('/api/huggingface/account')[1],{'connected':True,'username':'example'})
        self.assertFalse(self.request('/api/huggingface/disconnect',{})[1]['connected'])
    def test_download_uses_control_permission_and_csrf(self):
        self.server.model_downloads=MagicMock()
        self.server.model_downloads.start.return_value={'status':'downloading','model':'example/model'}
        payload={'model':'example/model','revision':'a'*40}
        self.assertEqual(self.request('/api/huggingface/download',payload,csrf=False)[0],403)
        self.server.model_downloads.start.assert_not_called()
        self.assertEqual(self.request('/api/huggingface/download',payload)[0],202)
        self.server.model_downloads.start.assert_called_once_with(payload)
    def test_bad_query_and_arbitrary_asset_paths_rejected(self):
        self.assertEqual(self.request('/api/huggingface/models?url=https://attacker.test')[0],400)
        self.assertEqual(self.request('/api/huggingface/avatar?author=../outside')[0],400)
    def test_encoder_decoder_query_reaches_the_hub_from_http(self):
        with patch.object(self.server.huggingface,'search',return_value={'models':[],'next_cursor':None}) as search:
            status,body=self.request('/api/huggingface/models?search=t5&author=google&kind=LLM&family=t5&sort=downloads&text_task=seq2seq&cursor=page2')
        self.assertEqual(status,200)
        self.assertEqual(search.call_args.args[0]['text_task'],'seq2seq')
        self.assertEqual(search.call_args.args[0]['cursor'],'page2')

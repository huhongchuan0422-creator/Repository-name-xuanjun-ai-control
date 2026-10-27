from __future__ import print_function

import os
import sys
import unittest

ROOT=os.path.realpath(os.path.join(os.path.dirname(__file__),'..'))
sys.path.insert(0,os.path.join(ROOT,'scripts'))
from task_center_mcp_free_model_gate import parse_zero_price_page


class FreeModelGateTests(unittest.TestCase):
    def page(self,prompt='0',completion='0',display='Qwen2.5-7B-Instruct (Free)'):
        return (r'''631:{\"price\":\"%s\",\"specification\":\"prompt\",\"unitOfGood\":\"/ M Tokens\"}\n'''+
          r'''632:{\"price\":\"%s\",\"specification\":\"completion\",\"unitOfGood\":\"/ M Tokens\"}\n'''+
          r'''630:[\"$631\",\"$632\"]\n'''+
          r'''622:{\"modelName\":\"Qwen/Qwen2.5-7B-Instruct\",\"price\":\"0\",\"currency\":\"¥\",\"DisplayName\":\"%s\",\"type\":\"text\",\"subType\":\"chat\",\"status\":\"normal\",\"targetModelName\":\"Qwen/Qwen2.5-7B-Instruct\",\"onlyByChargeBalance\":false,\"pricing\":\"$630\",\"priceUnit\":\"/ M Tokens\"}\n''')%(prompt,completion,display)

    def test_exact_free_chat_model_and_both_zero_prices_are_required(self):
        value=parse_zero_price_page(self.page().encode('utf-8'))
        self.assertEqual(value['model_id'],'Qwen/Qwen2.5-7B-Instruct')
        self.assertEqual((value['prompt_price'],value['completion_price']),('0','0'))
        self.assertEqual(value['only_by_charge_balance'],False)

    def test_nonzero_prompt_or_completion_is_rejected(self):
        for prompt,completion in (('1','0'),('0','1')):
            with self.assertRaisesRegex(ValueError,'ZERO_PROMPT_AND_COMPLETION'):
                parse_zero_price_page(self.page(prompt,completion).encode('utf-8'))

    def test_pro_or_changed_display_record_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'EXACT_FREE_MODEL_FIELDS'):
            parse_zero_price_page(self.page(display=
              'Qwen2.5-7B-Instruct (Pro)').encode('utf-8'))


if __name__=='__main__':unittest.main()

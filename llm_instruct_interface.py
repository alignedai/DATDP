from transformers import AutoTokenizer, AutoModelForCausalLM
import torch
from datetime import datetime
import sys


class LLMInstructCustomInterface():

    def __init__(self, model_dir="meta-llama/Meta-Llama-3-8B", tokenizer_dir=None):
        if tokenizer_dir is None:
            tokenizer_dir = model_dir
        self.tokenizer = AutoTokenizer.from_pretrained(tokenizer_dir, padding_side='left')
        self.model = AutoModelForCausalLM.from_pretrained(model_dir, device_map='auto')
        self.device = 'cuda'
        self.max_new_tokens = 5120

        self.tokenizer.pad_token = self.tokenizer.eos_token
        self.model.config.pad_token_id = self.model.config.eos_token_id
        self.model = self.model.eval()
        self.begin_text = '<|begin_of_text|>'
        self.start_header_id = '<|start_header_id|>'
        self.end_header_id = '<|end_header_id|>'
        self.end_of_role_text = '<|eot_id|>'
        self.end_of_text = '<|end_of_text|>'
        self.date = datetime.today().strftime('%Y-%m-%d')
        self.preamble = f'Cutting Knowledge Date: December 2023\nToday Date:{self.date}\n'
        self.terminators = [self.tokenizer.eos_token_id, self.tokenizer.convert_tokens_to_ids(self.end_of_role_text), self.tokenizer.convert_tokens_to_ids(self.end_of_text)]
        self.conversation = []

# See formatting from: https://www.llama.com/docs/model-cards-and-prompt-formats/llama3_1/

    def make_role_preamble(self, role_description):
        return self.begin_text + self.make_role('system', self.preamble + '\n' + role_description)

    def make_role(self, role, text):
        assert role in ['system', 'user', 'assistant']
        role_text = self.start_header_id + role + self.end_header_id + '\n\n'
        role_text += text + '\n' + self.end_of_role_text + '\n'
        return role_text

    def promptLLM(self, prompts, role_description='You are a helpful assistant', token_limit=None):
        description_prompt = self.make_role_preamble(role_description=role_description)
        instruct_prompts = [description_prompt + self.make_role('user', prompt) + '\n' for prompt in prompts]
        return self.completionBatch(instruct_prompts, token_limit)

    def completionBatch(self, prompts, token_limit=None):
        if len(prompts) == 0:
            print("Empty set of prompts submitted.", file=sys.stderr)
            return []
        if token_limit is None:
            token_limit = self.max_new_tokens
        with torch.inference_mode():
            inputs_ids = self.tokenizer(prompts, return_tensors='pt', padding=True).to(self.device)
            input_lengths = inputs_ids['input_ids'].size()[-1]
            outputs = self.model.generate(**inputs_ids, max_new_tokens=token_limit, do_sample=True, temperature=0.7, eos_token_id=self.terminators)
            trimmed_outputs = torch.stack([output[input_lengths:] for output in outputs])  # removes the initial prompts from the outputs
            responses = []
            for trimmed_output in trimmed_outputs:
                end_point = len(trimmed_output)
                while trimmed_output[end_point-1] in self.terminators and end_point > 0:  # this is to remove the terminators and padding from the end of the outputs
                    end_point -= 1
                responses = responses + self.tokenizer.batch_decode([trimmed_output[:end_point]], skip_special_tokens=False)
        assert len(prompts) == len(responses)
        del inputs_ids
        del outputs
        return responses



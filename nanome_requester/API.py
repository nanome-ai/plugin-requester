from nanome.util import Logs
from nanome.util.enums import NotificationTypes

import json
import os
import re
import requests
import tempfile

CONFIG_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'config.json'))
DEFAULT_TIMEOUT = 30

# attempt to load config
try:
    with open(CONFIG_PATH, 'r') as f:
        CONFIG = json.load(f)

except FileNotFoundError:
    raise Exception('Could not find config file at: ' + CONFIG_PATH)

except json.decoder.JSONDecodeError:
    raise Exception('Config file is not a valid JSON file')

# validate config
if 'endpoints' not in CONFIG:
    raise Exception('Missing endpoints in config')

ENDPOINTS = CONFIG['endpoints']
for endpoint in ENDPOINTS:
    for key in ['name', 'url', 'method', 'response']:
        if key not in endpoint:
            raise Exception(f'Endpoint missing key "{key}"')

    name = endpoint['name']
    prefix = f'Endpoint "{name}":'

    if endpoint['response'] not in ['json', 'file', 'text']:
            raise Exception(f'{prefix} Invalid response type "{endpoint["response"]}"')

    for input in endpoint.get('inputs', []):
        for key in ['name', 'type', 'label']:
            if key not in input:
                raise Exception(f'{prefix} Input missing key "{key}"')

        if input['type'] not in ['text', 'number', 'password', 'dropdown', 'toggle', 'molecule']:
            raise Exception(f'{prefix} Input "{input["name"]}" invalid type "{input["type"]}"')

        if input['type'] == 'dropdown':
            if 'items' not in input:
                raise Exception(f'{prefix} Input "{input["name"]}" missing "items"')

        if input['type'] == 'molecule':
            if 'format' not in input:
                raise Exception(f'{prefix} Input "{input["name"]}" missing "format"')

            if input['format'] not in ['pdb', 'sdf', 'mmcif', 'smiles']:
                raise Exception(f'{prefix} Input "{input["name"]}" invalid "format"')

    for output in endpoint.get('outputs', []):
        for key in ['name', 'type']:
            if key not in output:
                raise Exception(f'{prefix} Output missing key "{key}"')

        if output['type'] not in ['str', 'list', 'file']:
            raise Exception(f'{prefix} Invalid output type "{output["type"]}"')

        if endpoint['response'] == 'json' and 'path' not in output:
            raise Exception(f'{prefix} "json" response outputs must have "path"')

        if endpoint['response'] != 'json' and 'path' in output:
            raise Exception(f'{prefix} "{endpoint["response"]}" response outputs cannot have "path"')

        if endpoint['response'] == 'text' and 'regex' not in output:
            raise Exception(f'{prefix} "text" response outputs must have "regex"')

        if endpoint['response'] != 'text' and 'regex' in output:
            raise Exception(f'{prefix} "{endpoint["response"]}" response outputs cannot have "regex"')


class API:
    def __init__(self, plugin):
        self.plugin = plugin
        self.requests = []

        self.inputs = {}
        self.cache = {}

        self.session = requests.Session()
        self.temp_dir = tempfile.TemporaryDirectory()

    def reset(self):
        # start new session and clear temporary values
        self.session = requests.Session()
        self.requests.clear()
        self.inputs.clear()

        # remove items from cache that don't need to be remembered
        for key, output in list(self.cache.items()):
            if not output.get('cache'):
                del self.cache[key]

    def get_endpoint_by_output(self, token):
        for endpoint in ENDPOINTS:
            for output in endpoint.get('outputs', []):
                if output['name'] == token:
                    return endpoint

    def get_replacement_tokens(self, obj):
        # get all tokens that need to be replaced
        return set(re.findall(r'{{(.+?)}}', json.dumps(obj)))

    def list_endpoints(self):
        # list all non-hidden endpoints
        return [e for e in ENDPOINTS if not e.get('hidden')]

    def init_request(self, endpoint=None):
        # start new request or continue request chain
        if endpoint:
            self.requests.append(endpoint)
        else:
            endpoint = self.requests[-1]

        # get all replacement tokens and inputs
        tokens = self.get_replacement_tokens(endpoint)
        inputs = set(i['name'] for i in endpoint.get('inputs', []))

        # check if any non-input tokens are missing
        for token in tokens - inputs:
            if token not in self.cache:
                # if token is missing, init dependency request
                dependency = self.get_endpoint_by_output(token)
                if dependency is None:
                    self.handle_error(f'Endpoint for token not found: {token}')
                    return
                # recursively call init_request with dependency
                self.init_request(dependency)
                break
        else:
            # if all tokens are present, check inputs
            inputs = endpoint.get('inputs', [])
            if inputs:
                # replace any tokens in inputs, then prompt for values
                inputs = self.replace_tokens(inputs, self.cache)
                self.plugin.prompt_inputs(endpoint['name'], inputs)
            else:
                # all inputs are available, continue request
                self.continue_request()

    def continue_request(self):
        # prepare request with values from inputs and cache
        values = {**self.cache, **self.inputs}
        endpoint = self.replace_tokens(self.requests.pop(), values)
        self.inputs.clear()

        url = endpoint['url']
        method = endpoint['method']
        proxies = CONFIG.get('proxies')
        timeout = CONFIG.get('timeout', DEFAULT_TIMEOUT)
        headers = endpoint.get('headers')
        params = endpoint.get('params')
        files_body = endpoint.get('files')
        data_body = endpoint.get('data')
        json_body = endpoint.get('json')

        try:
            r = self.session.request(
                method, url, proxies=proxies, timeout=timeout, headers=headers,
                params=params, files=files_body, data=data_body, json=json_body, verify=False)
        except requests.exceptions.ConnectionError:
            self.handle_error('Connection error, check proxy settings.')
            return
        except requests.exceptions.Timeout:
            self.handle_error('Request timed out.')
            return

        Logs.debug(f'\n{endpoint["name"]}\n{r.url}\n{r.text}\n')

        if not r.ok:
            self.handle_error(f'Request failed: {r.reason}')
            return

        if endpoint['response'] == 'json':
            try:
                data = r.json()
            except json.decoder.JSONDecodeError:
                self.handle_error('Response is not valid JSON.')
                return
        elif endpoint['response'] == 'file':
            data = r.content
        else:
            data = r.text

        # add outputs to cache
        outputs = self.parse_outputs(data, endpoint)
        for output in outputs:
            self.cache[output['name']] = output
            Logs.debug(f'output {output["name"]}: {output["value"]}')

        # if request in queue, init next one
        if self.requests:
            self.init_request()
            return

        # otherwise this is last request, handle output
        if endpoint['response'] == 'file':
            # if response file, send to Nanome
            for output in endpoint.get('outputs', []):
                path = os.path.join(self.temp_dir.name, output['name'])
                with open(path, 'wb') as f:
                    f.write(data)
                self.plugin.send_files_to_load(path)
                self.plugin.show_endpoints()

        elif endpoint['response'] in ['json', 'text']:
            # if response text/json, display in UI
            self.plugin.render_output(outputs)

        self.reset()

    def replace_tokens(self, obj, values):
        # replace tokens in obj with values from values
        tokens = self.get_replacement_tokens(obj)
        string = json.dumps(obj)

        for token in tokens:
            if token not in values:
                raise Exception(f'Value not set: {token}')

            item = values[token]
            value = item['value']

            # convert bool to preferred representation
            if item['type'] == 'toggle' and 'values' in item:
                value = item['values'][value]

            # replace quoted token with literal value if non-str;
            # e.g. "key": "{{number}}" -> "key": 1
            if type(value) is not str:
                value = json.dumps(value)
                string = string.replace('"{{' + token + '}}"', value)

            # replace tokens with value
            string = string.replace('{{' + token + '}}', value)

        # strict=False allows for newlines in strings
        return json.loads(string, strict=False)

    def set_input_value(self, item, value):
        name = item['name']
        Logs.debug(f'input {name}: {value}')
        self.inputs[name] = {**item, 'value': value}

    def get_value_at_path(self, data, path):
        # get value at path in data, e.g. 'some.path[2].value'
        value = data

        try:
            for subpath in path.replace('][', '].[').split('.'):
                match = re.search(r'([^\[]+)?(?:\[(\d+)\])?', subpath)
                (key, index) = match.groups()

                if key is not None:
                    value = value[key]

                if index is not None:
                    value = value[int(index)]

        except (KeyError, IndexError):
            self.handle_error(f'Value not found: {path}', False)
            return None

        return value

    def parse_outputs(self, data, endpoint):
        # parse outputs from data, either with json path or regex for text
        outputs = []

        if endpoint['response'] == 'json':
            for output in endpoint.get('outputs', []):
                value = self.get_value_at_path(data, output['path'])
                outputs.append({**output, 'value': value})

        elif endpoint['response'] == 'text':
            for output in endpoint.get('outputs', []):
                regex = re.compile(output['regex'])
                value = regex.search(data).group(1)
                outputs.append({**output, 'value': value})

        return outputs

    def handle_error(self, msg, reset=True):
        self.plugin.send_notification(NotificationTypes.error, msg)
        Logs.error(msg)

        if reset:
            self.reset()
            self.plugin.show_endpoints()

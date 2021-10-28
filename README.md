# Nanome - Requester

A Nanome Plugin to make requests to APIs

## Dependencies

[Docker](https://docs.docker.com/get-docker/)

## Configuration

This plugin requires a `config.json` file at the root level to define the endpoints available to the user. The `config.json` file should contain the following fields:

| Property | Description |
| --- | --- |
| `endpoints` | Array of objects, defined in detail below. |
| `proxies` | (optional) Proxy settings for requests. [See example](#proxy) |
| `timeout` | (optional) Timeout for requests in seconds (default 30). |

### endpoints

At minimum, each endpoint must contain `name`, `url`, `method`, and `response`. All available properties are as follows:

| Property | Description |
| --- | --- |
| `name` | Name used to identify the endpoint in the UI. |
| `url` | URL of the endpoint. |
| `method` | HTTP method used to make the request. (e.g. `"GET"`, `"POST"`, etc.) |
| `response` | Response type to expect (`"json"`/`"text"`/`"file"`). |
| `hidden` | (optional) Bool to indicate whether or not the endpoint should be hidden from the UI. Useful for dependency endpoints such as for authentication. |
| `headers` | (optional) Headers to be sent with the request. |
| `params` | (optional) Query string parameters. |
| `data` | (optional) Form-encoded data to be included in body. |
| `json` | (optional) JSON-encoded data to be included in body. |
| `files` | (optional) Multipart-form-encoded files to be included in body. |
| `inputs` | (optional) Array of inputs to prompt user. |
| `outputs` | (optional) Array of outputs to be displayed to user or used for future requests. |

#### inputs

Inputs are used to prompt the user for input before making the request. The `inputs` array should contain objects with the following fields:

| Property | Description |
| --- | --- |
| `name` | Name of the input. (e.g. `"molecule_id"`) |
| `type` | Type of the input. (`"text"`/`"number"`/`"password"`/`"dropdown"`/`"toggle"`/`"molecule"`) |
| `label` | Label to display to the user. (e.g. `"Molecule ID"`) |
| `placeholder` | (optional) Placeholder text to display to the user. |
| `format` | (only for `molecule`) Format of the molecule. (`"pdb"`/`"sdf"`/`"mmcif"`/`"smiles"`) |
| `items` | (only for `dropdown`) Array of items to display to the user. |
| `values` | (only for `toggle`) Array of 2 values to be used for `Off`/`On`. (e.g. `["no", "yes"]`) |

#### outputs

Outputs are used to save values from the response for use in further requests, or to display to the user. The `outputs` array should contain objects with the following fields:

| Property | Description |
| --- | --- |
| `name` | Name of the output. (e.g. `"token"`) |
| `type` | Type of the output. (`"str"`/`"list"`/`"file"`) |
| `path` | (only for `json` response) Object path to find the value. (e.g. `"some.path[2].value"`) |
| `regex` | (only for `text` response) Regex with a capture group to find the value. (e.g. `"value: (\\d+)"`) |
| `label` | (optional) Label to display to the user. (e.g. `"Token"`) |
| `cache` | (optional) Save the output for future requests while plugin is active. (e.g. `true`) |

### Replacement Tokens

Any properties defined in an endpoint may contain any number of replacement tokens for dynamic values. These tokens are written as `{{token}}` and are replaced with the value of the corresponding input of the current endpoint or output from another endpoint. For example, if the endpoint `url` is `http://example.com/projects/{{project_id}}/files`, then the `url` will be replaced to contain the value of the `project_id` input.

Example:

```json
{
  "endpoints": [
    {
      "name": "Get Project",
      "url": "http://example.com/projects/{{project_id}}/files",
      "method": "GET",
      "response": "file",
      "inputs": [
        {
          "name": "project_id",
          "type": "text",
          "label": "Project ID"
        }
      ],
      "outputs": [
        {
          "name": "project_{{project_id}}.nanome",
          "type": "file"
        }
      ]
    }
  ]
}
```

### Dependant Requests

Replacement tokens in a request may come from the output of another request. The plugin will automatically make the request for endpoints that have an output matching the replacement token. It is important to give each output a unique name to prevent ambiguity with other requests.

A common dependant request example is authorization. In the following config, the "Authorization" endpoint is hidden from the list in the plugin. When the plugin user makes a request to the "Download Molecule" endpoint, the plugin will automatically make a request to the "Authorization" endpoint to get the "token" value required for the authorization header.

```json
{
  "endpoints": [
    {
      "name": "Authorization",
      "hidden": true,
      "url": "http://example.com/auth",
      "method": "POST",
      "response": "json",
      "body": {
        "username": "{{username}}",
        "password": "{{password}}"
      },
      "inputs": [
        {
          "name": "username",
          "type": "text",
          "label": "Username"
        },
        {
          "name": "password",
          "type": "password",
          "label": "Password"
        }
      ],
      "outputs": [
        {
          "name": "token",
          "type": "str",
          "path": "token.value",
          "label": "Token"
        }
      ]
    },
    {
      "name": "Download Molecule",
      "url": "http://example.com/molecules/{{molecule_id}}/sdf",
      "method": "GET",
      "response": "file",
      "headers": {
        "Authorization": "Bearer {{token}}"
      },
      "inputs": [
        {
          "name": "molecule_id",
          "type": "text",
          "label": "Molecule ID"
        }
      ],
      "outputs": [
        {
          "name": "{{molecule_id}}.sdf",
          "type": "file"
        }
      ]
    }
  ]
}
```

Another example is listing files in a project and loading one of them. In the following config, both the "List Projects" and "List Project Files" endpoints are hidden from the list in the plugin. When the plugin user makes a request to the "Load File from Project" endpoint, the plugin will automatically make a request to the "List Projects" endpoint to get the "projects" value required for the "Project" input of "List Project Files". It will then make a request to the "List Files" endpoint to get the "files" value required for the "File" input of "Load File from Project".

```json
{
  "endpoints": [
    {
      "name": "List Projects",
      "description": "Get list of projects",
      "hidden": true,
      "url": "http://example.com/projects",
      "method": "GET",
      "response": "json",
      "outputs": [
        {
          "name": "projects",
          "type": "list",
          "path": "projects"
        }
      ]
    },
    {
      "name": "List Project Files",
      "description": "Get list of files in a project",
      "hidden": true,
      "url": "http://example.com/projects/{{project}}/files",
      "method": "GET",
      "response": "json",
      "inputs": [
        {
          "name": "project",
          "type": "dropdown",
          "label": "Project",
          "items": "{{projects}}"
        }
      ],
      "outputs": [
        {
          "name": "files",
          "type": "list",
          "path": "files"
        }
      ]
    },
    {
      "name": "Load File from Project",
      "url": "http://example.com/projects/{{project}}/files/{{file}}/sdf",
      "method": "GET",
      "response": "file",
      "inputs": [
        {
          "name": "file",
          "type": "dropdown",
          "label": "File",
          "items": "{{files}}"
        }
      ],
      "outputs": [
        {
          "name": "{{file}}.sdf",
          "type": "file"
        }
      ]
    }
  ]
}
```

More examples of replacement tokens and dependant requests are included in the example config file `config.example.json`.

### Proxy

To use a proxy when making requests, add the following item to the plugin config, replacing the `example.com` and `8080`/`8443` with the proxy host and port(s):

```json
{
  "proxies": {
    "http": "http://example.com:8080",
    "https": "https://example.com:8443"
  }
}
```

## Usage

To run Requester in a Docker container:

```sh
$ cd docker
$ ./build.sh
$ ./deploy.sh -a <plugin_server_address> [optional args]
```

## Development

To run Requester with autoreload:

```sh
$ python3 -m pip install -r requirements.txt
$ python3 run.py -r -a <plugin_server_address> [optional args]
```

## License

MIT

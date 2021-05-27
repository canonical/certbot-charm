# certbot

## Description

Certbot is used to acquire and manage certificates from Let's Encrypt.

## Acquiring Certificates

The charm will attempt to acquire a certificate in the start hook, this
will only be successful if the charm has been configured for acquiring
certificates. The configuration parameters `agree-tos`, `domains`,
`email` & `plugin` must have all been set for this to work along with
any necessary plugin-specific settings.

### DNS-Google Plugin

Certbot's dns-google plugin uses the Google Cloud DNS API to prove
ownership of the requested domain. Documentation for the plugin can be
found at https://certbot-dns-google.readthedocs.io/en/stable/. This
plugin requires API credentials to be supplied either through the
`credentials` parameter on the `get-certificate` action, or from the
`dns-google-credentials` setting in the charm configuration.

To acquire a certificate using this plugin run a command like the
following:

```
$ juju run-action --wait certbot/0 get-certificate \
    agree-tos=true \
    credentials=`cat cred.json | base64 -w0` \
    domains=example.com \
    email=webmaster@example.com \
    plugin=dns-google
```

### DNS-RFC2136 Plugin

Certbot's dns-rfc2136 plugin uses the
[RFC2136](https://tools.ietf.org/html/rfc2136) dynamic updates system
to prove ownership of the requested domain. Documentation for the plugin
can be found at https://certbot-dns-rfc2136.readthedocs.io/en/stable/.
This plugin requires API credentials to be supplied either through the
`credentials` parameter on the `get-certificate` action, or from the
`dns-rfc2136-credentials` setting in the charm configuration.

To acquire a certificate using this plugin run a command like the
following:

```
$ juju run-action --wait certbot/0 get-certificate \
    agree-tos=true \
    credentials=`cat cred.ini | base64 -w0` \
    domains=example.com \
    email=webmaster@example.com \
    plugin=dns-rfc2136
```

### DNS-Route53 Plugin

Certbot's dns-route53 plugin uses the AWS Route53 API to prove
ownership of the requested domain. Documentation for the plugin can be
found at https://certbot-dns-route53.readthedocs.io/en/stable/. This
plugin requires API credentials to be supplied either through the
`aws-access-key-id` and `aws-secret-access-key` parameters on the
`get-certificate` action, or from the `dns-route53-aws-access-key-id`
and `dns-route63-aws-secret-access-key` settings in the charm
configuration.

To acquire a certificate using this plugin run a command like the
following:

```
$ juju run-action --wait certbot/0 get-certificate \
    agree-tos=true \
    aws-access-key-id=ABCDEFGHIJKLMNOPQRST \
    aws-secret-access-key=YcdqUfSGwvmIJAhjWNzGxSifdXr78RRqZrMnPxoz \    
    domains=example.com \
    email=webmaster@example.com \
    plugin=dns-route53
```

## Updating Deploy Configuration

Then the certificate deployment settings (`cert-path`, `chain-path`,
`combined-path`, `deploy-command`, `fullchain-path` or `key-path`) are
changed, those changes do not come into effect until either a new
certificate is acquired or an existing certificate is renewed. To apply
the changes to an existing certificate without waiting for a renewel use
the `deploy` action.

The `deploy` action requires a single parameter `domain` which is the
primary domain in the certificate, for example:

```
$ juju run-action --wait certbot/0 deploy domain=example.com
```

## Integrating With Web-Servers

### HAProxy

HAProxy uses a combined certificate chain and key file for its TLS
confguration. If the `combined-path` charm configuration setting is
configured then a suitable file will be created at that path. 

The easiest way to use this charm with the
[haproxy](https://jaas.ai/haproxy) charm is to set the following
configuration settings:

```
combined-path: /var/lib/haproxy/default.pem
deploy-command: systemctl reload haproxy
```

In the haproxy charm configuration set `services` to something like:

```
- service_name: app_https
  service_host: "0.0.0.0"
  service_port: 443
  service_options:
    - mode http
    - option httpchk GET / HTTP/1.0
  crts: [DEFAULT]
  server_options: check inter 2000 rise 2 fall 5 maxconn 4096
- service_name: api_http
  service_host: "0.0.0.0"
  service_port: 80
  service_options:
    - mode http
    - http-request redirect scheme https
```

## Notes about Scale Out
The units of a certbot application will make no attempt to communicate
with each other, and do not share certificates. This means that the
units will have to acquire certificates individually.

If the charm is configured to acquire certificates in the start hook
then there is a potential for units to race acquiring certificates. In
most cases this is not a problem. If a unit fails to acquire a
certificate in the start hook it charm will remain in the blocked state
and a certificate will have to be acquired using an action instead.

## Developing

Create and activate a virtualenv,
and install the development requirements,

    virtualenv -p python3 venv
    source venv/bin/activate
    pip install -r requirements-dev.txt

## Testing

Just run `run_tests`:

    ./run_tests

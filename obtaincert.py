from subprocess import call
from config import WEBHOOK_HOST

OPENSSL_CONFIG_TEMPLATE = """
prompt = no
distinguished_name = req_distinguished_name
req_extensions = v3_req
[ req_distinguished_name ]
C                      = RU
ST                     = Saint-Petersburg
L                      = Saint-Petersburg
O                      = tgvkbot
OU                     = tgvkbot
CN                     = %(domain)s
emailAddress           = tgvkbot@gmail.com
[ v3_req ]
# Extensions to add to a certificate request
basicConstraints = CA:FALSE
keyUsage = nonRepudiation, digitalSignature, keyEncipherment
subjectAltName = @alt_names
[ alt_names ]
DNS.1 = %(domain)s
DNS.2 = *.%(domain)s
"""

call([
    'openssl', 'genrsa', '-out', 'webhook_pkey.pem', '2048'
])
config = open('openssl_config', 'w')
config.write(OPENSSL_CONFIG_TEMPLATE % {'domain': WEBHOOK_HOST})
config.close()
call([
    'openssl', 'req', '-new', '-x509', '-days', '3650', '-key', 'webhook_pkey.pem', '-out', 'webhook_cert.pem',
    '-config', 'openssl_config'
])

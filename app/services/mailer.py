"""SMTP configuration. Password is kept only in a private server-side file."""
import json
import os
import re
import smtplib
import ssl
import tempfile
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from flask import current_app
from .. import db

_ready = False

def ensure():
    global _ready
    if not _ready:
        db.execute('CREATE TABLE IF NOT EXISTS sl_mail_settings (id INT PRIMARY KEY, config TEXT NOT NULL) ENGINE=InnoDB')
        _ready = True
DEFAULTS = dict(enabled=False, host='', port=587, security='starttls', username='', from_email='', from_name='Schoolink')


def secret_path():
    return Path(current_app.root_path).parent / '.secrets' / 'smtp-password'


def get_config():
    ensure()
    row = db.scalar('SELECT config FROM sl_mail_settings WHERE id=1', default='')
    try:
        data = json.loads(row) if row else {}
    except (ValueError, TypeError):
        data = {}
    return {**DEFAULTS, **{k:v for k,v in data.items() if k in DEFAULTS}}


def password_set():
    return secret_path().is_file()


def valid_email(value):
    return bool(re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', value or '')) and len(value) <= 150


def validate(form):
    host = (form.get('host') or '').strip()
    if not host or len(host) > 160 or not re.fullmatch(r'[a-zA-Z0-9.-]+', host):
        raise ValueError('Enter a valid SMTP hostname, such as smtp.example.com.')
    try:
        port = int(form.get('port', '587'))
        if not 1 <= port <= 65535:
            raise ValueError()
    except ValueError:
        raise ValueError('SMTP port must be between 1 and 65535.')
    security = form.get('security', 'starttls')
    if security not in ('starttls', 'ssl'):
        raise ValueError('Choose STARTTLS or SSL/TLS encryption.')
    sender = (form.get('from_email') or '').strip()
    name = (form.get('from_name') or 'Schoolink').strip()
    if not valid_email(sender) or any(c in name for c in '\r\n'):
        raise ValueError('Enter a valid sender email and name.')
    username = (form.get('username') or '').strip()
    if len(username) > 150 or len(name) > 100:
        raise ValueError('SMTP username or sender name is too long.')
    config = dict(enabled=bool(form.get('enabled')), host=host, port=port, security=security,
                  username=username, from_email=sender, from_name=name)
    password = form.get('smtp_password') or ''
    if len(password) > 1000:
        raise ValueError('SMTP password is too long.')
    if config['enabled'] and username and not password and (form.get('clear_password') or not password_set()):
        raise ValueError('Enter the SMTP password before enabling authenticated mail.')
    return config, password


def save(config, password='', clear=False):
    path = secret_path()
    if password:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.smtp-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(password)
            os.chmod(name, 0o600)
            os.replace(name, path)
        finally:
            if os.path.exists(name): os.unlink(name)
    elif clear:
        path.unlink(missing_ok=True)
    ensure()
    db.execute('INSERT INTO sl_mail_settings (id,config) VALUES (1,%s) ON DUPLICATE KEY UPDATE config=VALUES(config)', (json.dumps(config),))


def send_test(recipient):
    if not valid_email(recipient):
        raise ValueError('Enter a valid test recipient email.')
    config = get_config()
    if not config['enabled']:
        raise ValueError('Save and enable SMTP before sending a test email.')
    message = EmailMessage()
    message['Subject'] = 'Schoolink SMTP test'
    message['From'] = formataddr((config['from_name'], config['from_email']))
    message['To'] = recipient
    message.set_content('Your Schoolink SMTP settings are working. This test was requested from Mail settings.')
    transport = smtplib.SMTP_SSL if config['security'] == 'ssl' else smtplib.SMTP
    kwargs = {'timeout':12}
    if config['security'] == 'ssl': kwargs['context'] = ssl.create_default_context()
    with transport(config['host'], config['port'], **kwargs) as server:
        if config['security'] == 'starttls':
            server.ehlo(); server.starttls(context=ssl.create_default_context()); server.ehlo()
        if config['username']:
            password = secret_path().read_text() if password_set() else ''
            server.login(config['username'], password)
        server.send_message(message)

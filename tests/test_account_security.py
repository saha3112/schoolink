import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from flask import Flask
from app.services import user_access as U, mailer as M


def user(uid, role='1', permissions=None, reset=False):
    return dict(id=uid,user_type=role,is_admin=role in ('0','1','9'),
                _access=None if permissions is None else {'permissions':json.dumps(permissions),'reset_passwords':reset,'session_version':0})


class AccessTests(unittest.TestCase):
    def test_legacy_admin_and_super_keep_access(self):
        self.assertEqual(U.allowed_keys(user(1)),U.keys())
        self.assertTrue(U.endpoint_allowed(user(1,'0',[]),'admin.settings'))

    def test_restricted_admin_direct_routes_and_csv_are_blocked(self):
        actor=user(1,permissions=['admin.classes'])
        self.assertTrue(U.endpoint_allowed(actor,'admin.classes'))
        for endpoint in ('admin.settings','students.edit','reports.card','account.reset_password','security.smtp','media.api_upload'):
            self.assertFalse(U.endpoint_allowed(actor,endpoint),endpoint)
        self.assertFalse(U.endpoint_allowed(actor,'csvio.do_import',{'kind':'marks'}))
        self.assertTrue(U.endpoint_allowed(actor,'main.dashboard'))

    def test_admin_cannot_grant_or_reset_a_superior_or_self(self):
        restricted=user(1,permissions=['security.permissions','reset_passwords'])
        self.assertFalse(U.can_manage(restricted,user(2)))
        self.assertFalse(U.can_manage(restricted,restricted))
        self.assertFalse(U.can_reset(restricted,user(3,'0')))
        self.assertFalse(U.can_reset(restricted,user(2)))
        self.assertFalse(U.can_manage(user(1,'0'),user(3,'9')))
        self.assertTrue(U.can_manage(user(1,'0'),user(2)))

    def test_reset_delegation_only_reaches_staff_and_parents(self):
        delegate=user(1,'2',[],True)
        self.assertTrue(U.can_reset(delegate,user(2,'3',[])))
        self.assertTrue(U.can_reset(delegate,user(3,'2',[])))
        self.assertFalse(U.can_reset(delegate,user(4)))
        self.assertFalse(U.can_reset(delegate,user(5,'0')))
        self.assertFalse(U.can_reset(user(1,'2',[],False),user(2,'3',[])))

    def test_invalid_permission_json_fails_closed(self):
        actor=user(1,permissions=[]);actor['_access']['permissions']='broken'
        self.assertFalse(U.endpoint_allowed(actor,'admin.classes'))

    def test_attachment_permission_uses_its_owner(self):
        actor=user(1,permissions=['school.gallery'])
        with patch.object(U.db,'one',return_value={'owner_type':'work'}):
            self.assertFalse(U.endpoint_allowed(actor,'school.attachment_delete',{'fid':1}))
        with patch.object(U.db,'one',return_value={'owner_type':'album'}):
            self.assertTrue(U.endpoint_allowed(actor,'school.attachment_delete',{'fid':1}))


class MailTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__)
        self.context=self.app.app_context();self.context.push();self.addCleanup(self.context.pop)
        self.config=dict(M.DEFAULTS,enabled=True,host='smtp.example.com',username='school',from_email='school@example.com')

    def test_tls_and_sender_validation(self):
        for changes in ({'security':'none'},{'port':'70000'},{'from_email':'bad\r\nheader'},{'host':'https://example.com'}):
            with self.assertRaises(ValueError):M.validate({**self.config,**changes,'smtp_password':'secret'})

    def test_password_saved_privately_and_kept_when_blank(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(M,'secret_path',return_value=Path(folder)/'password'),patch.object(M,'ensure'),patch.object(M.db,'execute'):
            M.save(self.config,'private-value')
            path=Path(folder)/'password'
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            M.save(self.config,'')
            self.assertEqual(path.read_text(),'private-value')
            M.save(self.config,'',clear=True)
            self.assertFalse(path.exists())

    def test_send_uses_tls_and_never_places_password_in_message(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'password';path.write_text('private-value')
            with patch.object(M,'get_config',return_value=self.config),patch.object(M,'secret_path',return_value=path),patch.object(M.smtplib,'SMTP') as smtp:
                M.send_test('test@example.com')
                server=smtp.return_value.__enter__.return_value
                server.starttls.assert_called_once()
                server.login.assert_called_once_with('school','private-value')
                message=server.send_message.call_args.args[0]
                self.assertNotIn('private-value',message.as_string())

    def test_disabled_mail_does_not_connect(self):
        with patch.object(M,'get_config',return_value={**self.config,'enabled':False}),patch.object(M.smtplib,'SMTP') as smtp:
            with self.assertRaises(ValueError):M.send_test('test@example.com')
            smtp.assert_not_called()

if __name__=='__main__':unittest.main()

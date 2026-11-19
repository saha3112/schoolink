import unittest
from unittest.mock import patch
from app.services import parent_identity as P
from app.services import reportcard as R
from tools.recover_parent_names import recovery_plan


class ParentIdentityTests(unittest.TestCase):
    def test_real_parent_fields_take_priority_and_are_cleaned(self):
        row=dict(fname='  Rina&nbsp; ',mname=None,lname='<b>Das</b>',account_name='Other Name')
        self.assertEqual(P.name(row),'Rina Das')

    def test_valid_account_name_fallback(self):
        self.assertEqual(P.name(dict(fname=None,mname='',lname='',account_name=' Rina Das ')),'Rina Das')

    def test_codes_numbers_and_placeholder_names_are_not_people(self):
        for value in ('PAR12345','9916122093','Parent','null','None','—','0'):
            self.assertEqual(P.name(dict(fname=value,account_name='')),'',value)

    def test_blank_user_name_is_resolved_in_one_batch(self):
        with patch.object(P.db,'query',return_value=[dict(user_id='50',fname='Rina',lname='Das',mname='',account_name='')]) as query:
            self.assertEqual(P.for_users([50,50]),{50:'Rina Das'})
            query.assert_called_once()

    def test_report_cards_use_the_same_account_fallback(self):
        with patch.object(R.db,'query',return_value=[dict(fname=None,mname=None,lname=None,account_name='Rina Das',address='Road',phone_1='9000000001')]):
            self.assertEqual(R.parent_details(1)[0]['parentName'],'Rina Das')

    def test_recovery_requires_a_unique_verified_name(self):
        parents=[dict(id=1,user_id=10,fname=None,phone_1='+91 90000 00001'),dict(id=2,user_id=20,fname=None,phone_1='9000000002'),dict(id=3,user_id=30,fname='Existing Name',phone_1='9000000003')]
        sources=[dict(fname='Rina',lname='Das',phone_1='9000000001',_source='snapshot'),dict(fname='One Name',phone_1='9000000002',_source='snapshot'),dict(fname='Other Name',phone_1='9000000002',_source='other'),dict(fname='Replacement',phone_1='9000000003',_source='snapshot')]
        plan,missing,ambiguous=recovery_plan(parents,sources)
        self.assertEqual([p['id'] for p in plan],[1]);self.assertEqual(missing,[]);self.assertEqual(ambiguous,[2])

if __name__=='__main__':unittest.main()

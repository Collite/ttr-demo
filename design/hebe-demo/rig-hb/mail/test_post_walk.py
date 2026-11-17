"""Completed UI evidence cannot hide live thread, receipt-count or engine cleanup drift."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('he_s36_post_walk',Path(__file__).with_name('post_walk.py'))
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def fixture():
    steps={}
    threads=[]
    tasks=[]
    receipts=[]
    instances=[]
    for index,name in enumerate(('card_read','console_outcome','claimed_elsewhere','forward_start'),1):
        task,instance,root='task'+str(index),'instance'+str(index),'<root'+str(index)+'@example.test>'
        steps[name]={'taskId':task,'instanceId':instance,'rootMessageId':root}
        tasks.append({'task_id':task,'instance_id':instance,'state':'answered' if index<3 else 'gone'})
        instances.append({'id':instance,'state':'COMPLETED','activeTasks':0})
        threads.append({'root_message_id':root,'kind':'card' if index<4 else 'proposal','subject_ref':task if index<4 else 'proposal4','state':'closed'})
        args={'key':'hebe_p2_cert','instance':instance,'outcome':'started'}
        if index==4: args['channel']='email'
        receipts.append({'seq':index,'tool':'engine.start','ok':True,'argsRedacted':json.dumps(args)})
    steps['card_reply']={**steps['card_read'],'receiptId':'seq5'}
    steps['console_outcome']['receiptId']='seq6'
    steps['forward_start'].update(proposalId='proposal4',cleanupTaskId='task4')
    steps['bare_forward']={'rootMessageId':'<bare@example.test>'}
    threads.append({'root_message_id':'<bare@example.test>','kind':'chat','subject_ref':None,'state':'closed'})
    for seq,task in [(5,'task1'),(6,'task2')]:
        args={'outcome':'completed'}
        if seq==5: args['channel']='email'
        receipts.append({'seq':seq,'tool':'engine.answer','turnId':task,'ok':True,'argsRedacted':json.dumps(args)})
    return {'steps':steps},{'threads':threads,'tasks':tasks,'instances':instances},receipts


class LivePostWalk(unittest.TestCase):
    def test_complete_walk_still_needs_live_closed_matching_threads(self):
        record,state,receipts=fixture()
        self.assertEqual(audit.assess(record,state,receipts)[0],'PASS')
        for field,value in [('root_message_id','<crossed@example.test>'),('subject_ref','other-task'),('state','open')]:
            bad=copy.deepcopy(state);bad['threads'][0][field]=value
            self.assertEqual(audit.assess(record,bad,receipts)[0],'FAIL')

    def test_claim_elsewhere_does_not_prove_instance_cleanup(self):
        record,state,receipts=fixture()
        state['instances'][2].update(state='ACTIVE',activeTasks=1)
        self.assertEqual(audit.assess(record,state,receipts)[0],'FAIL')
        state['instances'][2].update(state='COMPLETED',activeTasks=0)
        state['tasks'][3]['instance_id']='wrong-instance'
        self.assertEqual(audit.assess(record,state,receipts)[0],'FAIL')

    def test_extra_start_answer_or_wrong_email_channel_fails(self):
        record,state,receipts=fixture()
        self.assertEqual(audit.assess(record,state,receipts+[receipts[0]])[0],'FAIL')
        self.assertEqual(audit.assess(record,state,receipts+[receipts[-1]])[0],'FAIL')
        bad=copy.deepcopy(receipts);bad[-2]['argsRedacted']='{"outcome":"completed"}'
        self.assertEqual(audit.assess(record,state,bad)[0],'FAIL')

    def test_missing_observation_or_incomplete_human_record_cannot_pass(self):
        record,state,receipts=fixture()
        del state['instances']
        self.assertEqual(audit.assess(record,state,receipts)[0],'OPEN')
        self.assertEqual(audit.verify(None,('OPEN','human walk incomplete')),('OPEN','human walk incomplete'))


if __name__=='__main__': unittest.main()

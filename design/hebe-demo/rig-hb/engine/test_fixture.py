"""The saved fixture follows HE §6a and PE's static role authorization contract."""
import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

B = '{http://www.omg.org/spec/BPMN/20100524/MODEL}'
C = '{http://camunda.org/schema/1.0/bpmn}'


class Fixture(unittest.TestCase):
    def test_role_form_details_and_async_boundary(self):
        root = ET.parse(Path(__file__).with_name('hebe-p2-cert.bpmn')).getroot()
        process = root.find(B + 'process')
        self.assertEqual(process.get(C + 'candidateStarterGroups'), 'hartland-sales-managers')
        self.assertEqual(process.get(C + 'historyTimeToLive'), 'P30D')
        self.assertEqual(process.find(B + 'startEvent').get(C + 'asyncAfter'), 'true')
        task, = process.findall(B + 'userTask')
        self.assertEqual(task.get(C + 'candidateGroups'), 'hartland-sales-managers')
        self.assertNotIn(C + 'candidateUsers', task.attrib)
        fields = task.findall('.//' + C + 'formField')
        self.assertEqual([(f.get('id'), f.get('type')) for f in fields],
                         [('outcome', 'enum'), ('note', 'string')])
        self.assertEqual([v.get('id') for v in fields[0]], ['approve', 'reject'])
        parameters = {p.get('name'): p.text for p in task.findall('.//' + C + 'inputParameter')}
        self.assertEqual(parameters['ttr_about'], '${execution.processBusinessKey}')
        expr = parameters['ttr_detail']
        self.assertTrue(expr.startswith("${'") and expr.endswith("'}"))
        rows = json.loads(expr[3:-2])
        self.assertEqual(len(rows), 12)
        self.assertEqual(len({r['položka'] for r in rows}), 12)
        self.assertFalse(process.findall('.//' + B + 'scriptTask'))


if __name__ == '__main__':
    unittest.main()

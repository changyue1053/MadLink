"""Local project and result-gate checks. No Xcode or simulator execution."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from project import generate
from session_results import REQUIRED, verify_session_results


class SessionAcceptance(unittest.TestCase):
    def fixture(self):
        return (dict(totalTestCount=2, passedTests=2, failedTests=0, skippedTests=0),
                {'testNodes': [{'children': [{'nodeType':'Test Case',
                    'nodeIdentifier':name+'()', 'result':'Passed'} for name in sorted(REQUIRED)]}]})

    def test_exact_named_results(self):
        verify_session_results(*self.fixture())

    def test_incomplete_wrong_and_duplicate_cases(self):
        summary, cases = self.fixture()
        for mutation in ('missing','extra','duplicate','skip','fail','unreported','wrong'):
            result = deepcopy(cases)
            nodes = result['testNodes'][0]['children']
            if mutation == 'missing': nodes.pop()
            elif mutation == 'extra': nodes.append(dict(nodes[0],nodeIdentifier='Unexpected/test'))
            elif mutation == 'duplicate': nodes[1] = nodes[0]
            elif mutation == 'skip': nodes[0]['result'] = 'Skipped'
            elif mutation == 'fail': nodes[0]['result'] = 'Failed'
            elif mutation == 'unreported': del nodes[0]['result']
            else: nodes[0]['nodeIdentifier'] = 'WrongClass/testInstalledSessionRecovery32Cycles'
            with self.assertRaises(ValueError): verify_session_results(summary,result)

    def test_summary_must_agree(self):
        summary, cases = self.fixture()
        for key in summary:
            with self.assertRaises(ValueError): verify_session_results(dict(summary,**{key:False}),cases)
        with self.assertRaises(ValueError): verify_session_results(dict(summary,passedTests=1),cases)

    def test_project_c_type_and_opt_in(self):
        with TemporaryDirectory() as t:
            root = Path(t)
            default, mobile = root/'default', root/'mobile'
            default.mkdir();mobile.mkdir()
            generate(default)
            generate(mobile,test_sources=('SessionTests.mm','SessionLifecycle.c'))
            base = 'Preview.xcodeproj/project.pbxproj'
            self.assertNotIn('SessionLifecycle',(default/base).read_text())
            p = (mobile/base).read_text()
            self.assertIn('"path" = "SessionLifecycle.c"; "lastKnownFileType" = "sourcecode.c.c"',p)
            self.assertIn('"path" = "SessionTests.mm"; "lastKnownFileType" = "sourcecode.cpp.objcpp"',p)


if __name__ == '__main__':
    unittest.main()

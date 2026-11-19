"""Exact named XCTest acceptance for the opt-in two-case simulator suite."""

REQUIRED = {
    'MadLinkTests/testSyntheticLifecycle',
    'MadLinkSessionTests/testInstalledSessionRecovery32Cycles',
}


def verify_session_results(summary, cases):
    for key, want in [('totalTestCount', 2), ('passedTests', 2),
                      ('failedTests', 0), ('skippedTests', 0)]:
        if type(summary.get(key)) is not int or summary[key] != want:
            raise ValueError('test counts')
    if summary.get('testStatus', 'Passed') != 'Passed' or summary.get('expectedFailures', 0) != 0:
        raise ValueError('test status')
    seen = set()

    def walk(nodes):
        if not isinstance(nodes, list):
            raise ValueError('test tree')
        for node in nodes:
            if not isinstance(node, dict) or node.get('result', 'Passed') != 'Passed':
                raise ValueError('test status')
            if node.get('nodeType') == 'Test Case':
                name = node.get('nodeIdentifier')
                if not isinstance(name, str):
                    raise ValueError('test identity')
                name = name.removesuffix('()')
                if name not in REQUIRED or name in seen or node.get('result') != 'Passed':
                    raise ValueError('test identity or result')
                seen.add(name)
            walk(node.get('children', []))

    walk(cases['testNodes'])
    if seen != REQUIRED:
        raise ValueError('missing test')

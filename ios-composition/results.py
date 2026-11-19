"""Exact one-case acceptance, no output of untrusted result values."""
def verify(summary, tree):
    counts={'totalTestCount':1,'passedTests':1,'failedTests':0,'skippedTests':0}
    if any(type(summary.get(k)) is not int or summary[k]!=v for k,v in counts.items()):
        raise ValueError('counts')
    if summary.get('expectedFailures',0)!=0:raise ValueError('expected failures')
    if summary.get('testStatus','Passed')!='Passed':raise ValueError('status')
    pending=tree['testNodes'].copy();seen=0
    while pending:
        node=pending.pop()
        if node.get('result','Passed')!='Passed':raise ValueError('node status')
        if node.get('nodeType')=='Test Case':
            allowed={'MadLinkCompositionTests/testSyntheticStatesReachRealRuntime',
                     'MadLinkCompositionTests/testSyntheticStatesReachRealRuntime()'}
            if node.get('nodeIdentifier') not in allowed or node.get('result')!='Passed':raise ValueError('case')
            seen+=1
        pending.extend(node.get('children',[]))
    if seen!=1:raise ValueError('case count')

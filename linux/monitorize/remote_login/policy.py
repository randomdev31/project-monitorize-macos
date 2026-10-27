"""Fail-closed session selection, independent of D-Bus and systemd effects."""


def session_target(sessions,uid):
    if not isinstance(sessions,list):return ('error',None)
    local=[]
    for s in sessions:
        if not isinstance(s,dict):return ('error',None)
        if s.get('seat')!='seat0':continue
        if type(s.get('uid')) is not int or not isinstance(s.get('id'),str):return ('error',None)
        local.append(s)
    if not local:return ('greeter',None)
    # No active capture can follow another account, even during overlapping logout.
    if any(s['uid']!=uid for s in local):return ('suspended',None)
    eligible=[s for s in local if s.get('active') is True and s.get('remote') is False
              and s.get('type') in ('wayland','x11')]
    if len(eligible)!=1:return ('suspended',None)
    return ('desktop',eligible[0]['id'])

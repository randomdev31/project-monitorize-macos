"""Verified greeter context, independent of desktop controller ownership."""
from .logind import LogindSessions,ROOT,MANAGER,SESSION


def greeter_context(bus):
    snapshot=LogindSessions(bus).snapshot()
    if snapshot['sessions'] or not snapshot['greeter_ready']:
        raise PermissionError('No active isolated greeter; zero-output startup may be unsupported.')
    found=[]
    for row in bus.call(ROOT,MANAGER,'ListSessions'):
        if row[3]!='seat0':continue
        values=bus.properties(row[4],SESSION)
        if (values.get('Class')=='greeter' and values.get('Active') and not values.get('Remote')
            and values.get('Seat',('',))[0]=='seat0' and values.get('Type') in ('wayland','x11')):
            found.append(dict(session=str(values['Id']),greeter_uid=int(values['User'][0])))
    if len(found)!=1:raise PermissionError('A unique active graphical greeter is required.')
    return found[0]

"""Verified greeter context, independent of desktop controller ownership."""
from .logind import LogindSessions,ROOT,MANAGER,SESSION


def greeter_context(bus,*,isolate_uid=False):
    snapshot=LogindSessions(bus).snapshot()
    if snapshot['sessions'] or not snapshot['greeter_ready']:
        raise PermissionError('No active isolated greeter; zero-output startup may be unsupported.')
    found=[]
    rows=bus.call(ROOT,MANAGER,'ListSessions')
    if len(rows)>64:raise PermissionError('Too many sessions to verify the greeter.')
    for row in rows:
        if row[3]!='seat0':continue
        values=bus.properties(row[4],SESSION)
        if (values.get('Class')=='greeter' and values.get('Active') and not values.get('Remote')
            and values.get('Seat',('',))[0]=='seat0' and values.get('Type') in ('wayland','x11')):
            found.append(dict(session=str(values['Id']),greeter_uid=int(values['User'][0]),session_type=str(values['Type'])))
    if len(found)!=1:raise PermissionError('A unique active graphical greeter is required.')
    context=found[0]
    if isolate_uid:
        # The greeter compositor can live in a per-UID user service rather than the
        # session scope. Its per-UID bus/socket evidence is usable only when no
        # other graphical session (including another seat or closing greeter)
        # shares that UID. Every gate rechecks this around display activation.
        graphical=[]
        for row in rows:
            if int(row[1])!=context['greeter_uid']:continue
            values=bus.properties(row[4],SESSION)
            if values.get('Type') in ('wayland','x11'):
                graphical.append(str(values.get('Id','')))
        if graphical!=[context['session']]:
            raise PermissionError('This compositor requires an isolated greeter account with one graphical session across all seats.')
    if not isolate_uid:context.pop('session_type',None)
    return context

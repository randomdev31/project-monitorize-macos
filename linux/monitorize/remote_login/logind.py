"""Read-only logind snapshots and D-Bus caller/session authentication.

Transport must use the system bus, bounded calls, and unique sender names supplied
by D-Bus itself. UI arguments are never accepted as caller UID/PID/session evidence.
"""
from pathlib import Path
import re

LOGIN='org.freedesktop.login1'
MANAGER=LOGIN+'.Manager'
SESSION=LOGIN+'.Session'
ROOT='/org/freedesktop/login1'
BUS='org.freedesktop.DBus'
USER_CLASSES=('user','user-early','user-incomplete')


class LogindSessions:
    def __init__(self,bus,*,cgroup_reader=lambda pid:Path(f'/proc/{pid}/cgroup').read_text()):
        self.bus=bus;self.cgroup_reader=cgroup_reader

    def authenticate(self,sender,selected_uid):
        if not isinstance(sender,str) or not sender.startswith(':'):
            raise PermissionError('A unique system-bus caller is required.')
        try:
            uid=int(self.bus.call('/org/freedesktop/DBus',BUS,'GetConnectionUnixUser',sender))
            pid=int(self.bus.call('/org/freedesktop/DBus',BUS,'GetConnectionUnixProcessID',sender))
            if uid!=selected_uid or pid<=0:raise ValueError()
            try:
                path=self.bus.call(ROOT,MANAGER,'GetSessionByPID',pid)
            except Exception as error:
                name=error.get_dbus_name() if hasattr(error,'get_dbus_name') else ''
                if name!='org.freedesktop.login1.NoSessionForPID':raise
                # systemd user services live under user@UID.service, outside the
                # session scope. The fixed controller and graphical application
                # scopes (including terminals) use the UID's verified Display.
                groups=self.cgroup_reader(pid).splitlines()
                prefix=f'/user.slice/user-{uid}.slice/user@{uid}.service/'
                valid=False
                for line in groups:
                    if not line.startswith('0::'+prefix):continue
                    relative=line[len('0::'+prefix):].split('/')
                    if (len(relative)>=2 and relative[0]=='app.slice' and
                        (relative[1:] == ['monitorize-remote-controller.service'] or
                         re.fullmatch(r'app-[^/]+\.(?:scope|service)',relative[1]))):
                        valid=True;break
                if not valid:raise ValueError()
                user_path=self.bus.call(ROOT,MANAGER,'GetUserByPID',pid)
                user=self.bus.properties(user_path,LOGIN+'.User')
                if int(user['UID'])!=uid or not user['Display'][0]:raise ValueError()
                path=user['Display'][1]
            values=self.bus.properties(path,SESSION)
            if (int(values['User'][0])!=uid or values['Seat'][0]!='seat0' or
                not values['Active'] or values['Remote'] or values['Type'] not in ('wayland','x11') or
                values['Class'] not in USER_CLASSES or not values['Id']):raise ValueError()
            return dict(uid=uid,pid=pid,session=str(values['Id']))
        except Exception:
            raise PermissionError('Caller is not the selected active local graphical session.') from None

    def snapshot(self):
        rows=self.bus.call(ROOT,MANAGER,'ListSessions')
        if len(rows)>64:raise ValueError('Too many sessions to verify remote-login ownership.')
        sessions=[];greeter=False
        for row in rows:
            if len(row)!=5:raise ValueError('Invalid logind session list.')
            _id,_uid,_name,seat,path=row
            if seat!='seat0':continue
            values=self.bus.properties(path,SESSION)
            kind=values.get('Class')
            if kind=='manager':continue
            if kind=='greeter':
                if values.get('Active') and not values.get('Remote') and values.get('Seat',('',))[0]=='seat0':
                    greeter=True
                continue
            if kind not in USER_CLASSES:raise ValueError('Unknown seat session class; capture suspended.')
            sessions.append(dict(id=str(values['Id']),uid=int(values['User'][0]),
                seat=str(values['Seat'][0]),active=bool(values['Active']),remote=bool(values['Remote']),
                type=str(values['Type']),locked=bool(values.get('LockedHint',False))))
        return dict(sessions=sessions,greeter_ready=greeter)

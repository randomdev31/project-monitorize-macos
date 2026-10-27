"""Bounded greeter activation using an authenticated host-helper context."""
from pathlib import Path
from .display_managers import require_manager,COMPOSITORS


def greeter_environment(settings,context,helper):
    capability=require_manager(getattr(settings,'manager','plasmalogin.service'))
    if capability['manager'] in ('gdm.service','plasmalogin.service'):
        # logind authenticates the session; the compositor verifier resolves its
        # own bus/socket, including services outside the session scope.
        if context.get('session_type')!='wayland':
            raise RuntimeError('Remote login requires a verified Wayland greeter.')
        return context['session'],{'XDG_SESSION_TYPE':'wayland'}
    return helper._active_session(context['greeter_uid'])


def greeter_compositor(settings, context, session, environment, helper):
    capability=require_manager(getattr(settings,'manager','plasmalogin.service'))
    if session!=context['session'] or environment.get('XDG_SESSION_TYPE')!='wayland':
        raise PermissionError('Greeter is no longer the authenticated Wayland session.')
    expected=capability['compositor']
    if capability['manager']=='gdm.service':
        from .gdm_context import verify
        environment.update(verify(context,session,environment,helper))
    elif capability['manager']=='sddm.service':
        # The configured command is only a hint. Verify the actual Wayland
        # server peer belongs to the greeter's UID/session and matches it.
        name=environment.get('WAYLAND_DISPLAY','')
        if not name:raise RuntimeError('SDDM greeter Wayland socket could not be resolved.')
        socket=Path(name)
        if not socket.is_absolute():socket=Path('/run/user')/str(context['greeter_uid'])/socket
        pid=helper._validate_session_socket(socket,context['greeter_uid'],session)
        actual=COMPOSITORS.get(Path('/proc/'+str(pid)+'/exe').resolve().name,'unknown')
        if actual!=expected:raise RuntimeError('Running SDDM compositor does not match its verified configuration.')
    elif capability['manager']=='plasmalogin.service':
        from .kwin_context import verify
        environment.update(verify(context,session,environment,helper))
    else:raise RuntimeError('Unsupported greeter compositor.')
    return expected


def activate_greeter(settings,context,session,environment,output,remaining,helper,check):
    compositor=greeter_compositor(settings,context,session,environment,helper)
    if compositor=='weston':
        raise RuntimeError('Weston did not activate the reserved output through DRM hotplug. This configuration needs a validated activation adapter.')
    check()
    environment=dict(environment,XDG_CURRENT_DESKTOP={'kde':'KDE','hyprland':'Hyprland','gnome':'GNOME'}[compositor])
    if remaining<=1:raise RuntimeError('Greeter activation budget exhausted.')
    result=helper._run_worker(context['greeter_uid'],environment,dict(action='activate',name=output['name'],
        card=output['card'],connector_id=output['connector_id'],mode=[1920,1080,60],snapshot=None),timeout=min(10,remaining-1))
    if compositor=='gnome':
        from .gdm_context import verify
        verify(context,session,environment,helper)
    elif getattr(settings,'manager','plasmalogin.service')=='plasmalogin.service':
        from .kwin_context import verify
        verify(context,session,environment,helper)
    check()
    return result


def capture_operation(settings,context,operation,helper,check,virtual):
    """Existing-display capture is the default; virtual login is explicit opt-in."""
    if not getattr(settings,'create_login_virtual_display',False):
        from .login_primary import operation as primary_operation
        return primary_operation(settings,context,operation,helper,check)
    return virtual()

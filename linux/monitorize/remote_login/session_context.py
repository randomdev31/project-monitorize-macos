"""Whitelist root-resolved desktop metadata; never accept arbitrary environment."""

def desktop_context(environment):
    if environment.get('XDG_SESSION_TYPE')!='wayland':
        raise ValueError('Remote login currently requires a Wayland desktop session.')
    desktop=environment.get('XDG_CURRENT_DESKTOP','').lower().split(':')
    if any(value in ('kde','plasma') for value in desktop):value='KDE'
    elif 'hyprland' in desktop:value='Hyprland'
    elif 'gnome' in desktop:value='GNOME'
    else:raise ValueError('This desktop has no validated remote-login activation/layout adapter.')
    return {'desktop':value}

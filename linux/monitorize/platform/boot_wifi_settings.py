"""Pure, narrowly scoped personal Wi-Fi profile conversion; no networking I/O."""
import hashlib
import json
import re
import uuid as uuid_module


def _label(value):
    if isinstance(value, (bytes, bytearray)):
        value=value.decode('utf-8','replace')
    return ''.join(c if c.isprintable() else ' ' for c in str(value))[:160]


def _eligibility(settings):
    connection=settings.get('connection',{})
    try:uuid_module.UUID(str(connection.get('uuid','')))
    except (ValueError,AttributeError):return 'Profile has no valid UUID.'
    if connection.get('type') != '802-11-wireless':return 'Select a Wi-Fi profile.'
    if connection.get('read-only',False):return 'This profile is read-only.'
    if '802-1x' in settings:return 'Enterprise Wi-Fi is not supported by this setup.'
    wireless=settings.get('802-11-wireless',{})
    if wireless.get('mode','infrastructure') != 'infrastructure':return 'Hotspot and ad-hoc profiles are not supported.'
    if settings.get('802-11-wireless-security',{}).get('key-mgmt') not in ('wpa-psk','sae'):
        return 'Only personal WPA2/WPA3 Wi-Fi profiles are supported.'
    return ''


def describe_profile(settings, *, active, version, persistent):
    connection=settings.get('connection',{})
    security=settings.get('802-11-wireless-security',{})
    reason=_eligibility(settings)
    if not persistent:reason=reason or 'Profile is not saved persistently; save it in your network settings first.'
    if not isinstance(version,int) or isinstance(version,bool) or version<=0:
        reason=reason or 'NetworkManager profile version is unavailable.'
    matches=bool(connection.get('autoconnect',True) and not connection.get('permissions',[]) and
                 int(security.get('psk-flags',0)) == 0)
    return dict(uuid=str(connection.get('uuid','')),name=_label(connection.get('id','Wi-Fi')),
        interface=_label(connection.get('interface-name','')),security=str(security.get('key-mgmt','')),
        active=bool(active),version=str(version),persistent=bool(persistent),eligible=not reason,
        reason=reason,configuration='configuration_matches' if matches else 'needs_setup',
        boot_verified=False)


def _copy_settings(value):
    # copy.deepcopy(dbus.Array/Dictionary) discards empty-container signatures.
    # Preserve their wire types while creating independent mutable containers.
    if isinstance(value,dict):
        items={key:_copy_settings(item) for key,item in value.items()}
        if hasattr(value,'signature'):
            return type(value)(items,signature=value.signature,variant_level=value.variant_level)
        return items
    if isinstance(value,list):
        items=[_copy_settings(item) for item in value]
        if hasattr(value,'signature'):
            return type(value)(items,signature=value.signature,variant_level=value.variant_level)
        return items
    if isinstance(value,tuple):return tuple(_copy_settings(item) for item in value)
    if isinstance(value,bytearray):return bytearray(value)
    return value


def build_boot_wifi_update(settings,password):
    reason=_eligibility(settings)
    if reason:raise ValueError(reason)
    if not isinstance(password,str) or not password or any(not c.isprintable() for c in password):
        raise ValueError('Enter a valid Wi-Fi password; control characters are not supported.')
    security=settings['802-11-wireless-security']['key-mgmt']
    if security=='wpa-psk':
        valid=(8<=len(password)<=63 and password.isascii()) or bool(re.fullmatch(r'[0-9a-fA-F]{64}',password))
    else:
        valid=1<=len(password.encode('utf-8'))<=63
    if not valid:raise ValueError('Check the password length and format for this Wi-Fi security type.')
    result=_copy_settings(settings)
    result['connection']['autoconnect']=True
    result['connection']['permissions']=[]
    result['802-11-wireless-security']['psk-flags']=0
    result['802-11-wireless-security']['psk']=password
    return result


def settings_fingerprint(settings):
    def clean(value):
        if isinstance(value,dict):
            return {str(k):clean(v) for k,v in value.items()
                    if str(k).lower() not in ('psk','password','password-raw','private-key-password')}
        if isinstance(value,(bytes,bytearray)):return list(value)
        if isinstance(value,(list,tuple)):return [clean(v) for v in value]
        if isinstance(value,(str,int,float,bool)) or value is None:return value
        return str(value)
    return hashlib.sha256(json.dumps(clean(settings),sort_keys=True).encode()).hexdigest()

"""Strict public metadata boundary for the fixed observer, not an admission."""
def validate_observation(data, expected, nonce):
    def need(value):
        if not value:
            raise ValueError('WRITER_OBSERVATION_SCHEMA')
    def fields(value, keys):
        need(type(value) is dict and set(value) == set(keys.split()))
    def integer(value, limit=2**64):
        need(type(value) is int and 0 <= value < limit)
    def boolean(value):
        need(type(value) is bool)
    def digest(value):
        need(type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value))
    def rootnames(value):
        need(type(value) is list and 0 < len(value) <= 5 and value == sorted(set(value)))
        need(all(x in ('portal', 'operations', 'database', 'workspace', 'external_operations') for x in value))
    fields(data, 'hostname uid nonce observed_at scope roots samples units scheduler_metadata authoritative_writer enforced_fence inflight_drained database_opened service_actions business_requests limitations')
    need(data['hostname'] == expected and data['nonce'] == nonce)
    need(type(data['uid']) is int and data['uid'] == 0)
    need(type(data['observed_at']) is str and 19 <= len(data['observed_at']) <= 40
         and all(c in '0123456789T:.Z-' for c in data['observed_at']))
    need(data['scope'] == 'PR99_OPEN_HANDLE_OBSERVATION_NOT_AUTHORITY_OR_FENCE')
    need(data['authoritative_writer'] == data['enforced_fence'] == 'UNKNOWN')
    need(data['inflight_drained'] is False and data['database_opened'] is False)
    need(type(data['service_actions']) is int and data['service_actions'] == 0)
    need(type(data['business_requests']) is int and data['business_requests'] == 0)
    need(data['limitations'] == ['IDLE_WRITERS_NOT_EXCLUDED', 'SCHEDULER_CONTENTS_NOT_READ',
                                'OTHER_MOUNT_NAMESPACES_NOT_PROVEN', 'NO_STOP_OR_DRAIN_PERFORMED'])
    need(type(data['roots']) is list and len(data['roots']) == 5)
    for row, name in zip(data['roots'], ('portal', 'operations', 'database', 'workspace', 'external_operations')):
        fields(row, 'root present device inode' if row.get('present') is True else 'root present')
        need(row['root'] == name)
        boolean(row['present'])
        if row['present']:
            integer(row['device']); integer(row['inode'])
    need(type(data['samples']) is list and len(data['samples']) == 2)
    for sample in data['samples']:
        fields(sample, 'counts processes')
        fields(sample['counts'], 'processes fds vanished unreadable pid_identity_changed')
        for value in sample['counts'].values():
            integer(value, 131072)
        need(type(sample['processes']) is list and len(sample['processes']) <= 128)
        pids = set()
        for row in sample['processes']:
            fields(row, 'pid ppid start_ticks uid tags cgroup_sha256 handles shared_writable_mappings')
            for key in ('pid', 'ppid', 'start_ticks', 'uid'):
                integer(row[key])
            need(row['pid'] > 0 and row['pid'] not in pids)
            pids.add(row['pid'])
            digest(row['cgroup_sha256'])
            need(type(row['tags']) is list and len(row['tags']) <= 6)
            need(all(type(x) is int and 0 <= x < 6 for x in row['tags']))
            need(row['tags'] == sorted(set(row['tags'])))
            need(type(row['handles']) is list and len(row['handles']) <= 256)
            need(type(row['shared_writable_mappings']) is list and len(row['shared_writable_mappings']) <= 256)
            for handle in row['handles']:
                fields(handle, 'fd roots writable deleted device inode')
                for key in ('fd', 'device', 'inode'):
                    integer(handle[key])
                rootnames(handle['roots']); boolean(handle['writable']); boolean(handle['deleted'])
            for mapping in row['shared_writable_mappings']:
                fields(mapping, 'roots deleted')
                rootnames(mapping['roots']); boolean(mapping['deleted'])
    units = ('secure-secrets-portal.service', 'xuanjun-wecom-customer-contact.service',
             'xuanjun-wecom-customer-service.service', 'xuanjun-pr99-domestic-portal.service',
             'xuanjun-pr99-domestic-contact.service', 'xuanjun-pr99-domestic-customer-service.service')
    need(type(data['units']) is list and len(data['units']) == len(units))
    for row, name in zip(data['units'], units):
        fields(row, 'unit returncode load active pid cgroup_sha256')
        need(row['unit'] == name)
        need(type(row['returncode']) is int and -128 <= row['returncode'] <= 255)
        need(row['load'] in ('loaded', 'not-found', 'masked', 'error', 'bad-setting', 'UNKNOWN'))
        need(row['active'] in ('active', 'inactive', 'failed', 'activating', 'deactivating', 'reloading', 'UNKNOWN'))
        integer(row['pid']); digest(row['cgroup_sha256'])
    need(type(data['scheduler_metadata']) is list and len(data['scheduler_metadata']) == 4)
    for index, row in enumerate(data['scheduler_metadata']):
        fields(row, 'slot present mode uid size symlink' if row.get('present') is True else 'slot present')
        integer(row['slot']); need(row['slot'] == index); boolean(row['present'])
        if row['present']:
            for key in ('mode', 'uid', 'size'):
                integer(row[key])
            boolean(row['symlink'])
    return data

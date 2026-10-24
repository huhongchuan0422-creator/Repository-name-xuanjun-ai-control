"""Capture the initialized repository's actual engine binding inside its process.

No environment/default evaluator, database connection, source import, new file,
controller or authority is created. Call from the original admitted app hook.
This only resolves its database location; it does not prove all writers or data.
"""
import hashlib
import json
import os
from pathlib import PurePosixPath

from ingress_gate import runtime_identity


REPOSITORY_SOURCE_SHA256='8e133d4b07b0d6698befb2f0c9c98963a2d1156f58fa9e2c2a0fe4879bbf9104'


class ConfigurationBindingHold(RuntimeError):
    pass


def need(ok,code):
    if not ok:raise ConfigurationBindingHold(code)


def capture_repository_database(repository,verify_original_repository):
    """Use the factory ALREADY attached to this repository, not SessionLocal anew.

    verify_original_repository must bind this exact instance, originating app,
    startup/source and original fd/controller context. Its source/hash alone is
    insufficient. The returned record is private technical input, not a permit.
    """
    need(callable(verify_original_repository),'ORIGINAL_REPOSITORY_VERIFIER_REQUIRED')
    process=runtime_identity()
    need(verify_original_repository(repository,process,REPOSITORY_SOURCE_SHA256)is True,
         'ORIGINAL_RUNTIME_REPOSITORY_UNPROVEN')
    factory=getattr(repository,'session_factory',None)
    options=getattr(factory,'kw',None)
    need(type(options)is dict and options.get('bind')is not None,'INITIALIZED_SESSION_FACTORY_REQUIRED')
    need(options.get('binds')is None or options.get('binds')=={},'MULTIPLE_ENGINE_BINDINGS_UNRESOLVED')
    engine=options['bind'];url=getattr(engine,'url',None)
    need(url is not None and getattr(url,'drivername',None)in('sqlite','sqlite+pysqlite'),
         'FILE_SQLITE_ENGINE_REQUIRED')
    # Reject URI/query/remote configurations rather than stripping information
    # and pretending a different local database is the initialized target.
    need(not getattr(url,'query',None) and all(getattr(url,k,None)is None for k in
         ('username','password','host','port')),'SQLITE_OPTIONS_OR_REMOTE_BINDING_UNRESOLVED')
    path=getattr(url,'database',None)
    need(type(path)is str and path and path!=':memory:' and '\x00' not in path and
         not path.startswith('file:'),'DATABASE_LOCATION_UNRESOLVED')
    initialized_database=path
    initialized_driver=url.drivername
    cwd=os.getcwd()
    path=os.path.normpath(path if path.startswith('/') else os.path.join(cwd,path))
    need(path.startswith('/opt/trading-system/') and str(PurePosixPath(path))==path,
         'DATABASE_OUTSIDE_ORIGINAL_PROJECT')
    # Keep the very same factory/engine/options objects through observation.
    need(getattr(repository,'session_factory',None)is factory and getattr(factory,'kw',None)is options and
         options.get('bind')is engine and getattr(engine,'url',None)is url and
         getattr(url,'database',None)==initialized_database and
         runtime_identity()==process and os.getcwd()==cwd,
         'RUNTIME_DATABASE_BINDING_CHANGED')
    need(verify_original_repository(repository,process,REPOSITORY_SOURCE_SHA256)is True,
         'ORIGINAL_RUNTIME_BINDING_WITHDRAWN')
    need(getattr(repository,'session_factory',None)is factory and getattr(factory,'kw',None)is options and
         options.get('bind')is engine and getattr(engine,'url',None)is url and
         getattr(url,'database',None)==initialized_database and getattr(url,'drivername',None)==initialized_driver and
         not getattr(url,'query',None) and all(getattr(url,k,None)is None for k in
         ('username','password','host','port')) and
         (options.get('binds')is None or options.get('binds')=={}) and runtime_identity()==process and os.getcwd()==cwd,
         'RUNTIME_DATABASE_BINDING_CHANGED')
    record={'scope':'PR99_ACTUAL_REPOSITORY_ENGINE_LOCATION_NOT_COMPLETE_CATALOGUE',
      'process':process,'repository_source_sha256':REPOSITORY_SOURCE_SHA256,
      'database_path':path,'sidecars':{'wal':path+'-wal','shm':path+'-shm','journal':path+'-journal'},
      'derived_from_environment_or_defaults':False,'database_opened':False,
      'all_writers_proven':False,'fence_enforced':False,'production_migration_started':False}
    record['record_sha256']=hashlib.sha256((json.dumps(record,sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest()
    return record

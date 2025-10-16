# WMS-DU

Minimal skeleton: FastAPI + Docker Compose + GitHub Actions.
# Test trigger CI at 2025年 09月 22日 星期一 20:31:00 CST
# Trigger after permission change 2025年 09月 22日 星期一 20:34:03 CST
# keepalive

```
wms-du
├─ .mypy_cache
│  ├─ 3.12
│  │  ├─ @plugins_snapshot.json
│  │  ├─ __future__.data.json
│  │  ├─ __future__.meta.json
│  │  ├─ _ast.data.json
│  │  ├─ _ast.meta.json
│  │  ├─ _codecs.data.json
│  │  ├─ _codecs.meta.json
│  │  ├─ _collections_abc.data.json
│  │  ├─ _collections_abc.meta.json
│  │  ├─ _decimal.data.json
│  │  ├─ _decimal.meta.json
│  │  ├─ _operator.data.json
│  │  ├─ _operator.meta.json
│  │  ├─ _thread.data.json
│  │  ├─ _thread.meta.json
│  │  ├─ _typeshed
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  ├─ importlib.data.json
│  │  │  └─ importlib.meta.json
│  │  ├─ _warnings.data.json
│  │  ├─ _warnings.meta.json
│  │  ├─ _weakref.data.json
│  │  ├─ _weakref.meta.json
│  │  ├─ _weakrefset.data.json
│  │  ├─ _weakrefset.meta.json
│  │  ├─ abc.data.json
│  │  ├─ abc.meta.json
│  │  ├─ alembic
│  │  │  ├─ versions.data.json
│  │  │  └─ versions.meta.json
│  │  ├─ alembic.data.json
│  │  ├─ alembic.meta.json
│  │  ├─ annotated_types
│  │  │  ├─ __init__.data.json
│  │  │  └─ __init__.meta.json
│  │  ├─ app
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  ├─ db.data.json
│  │  │  ├─ db.meta.json
│  │  │  ├─ export_openapi.data.json
│  │  │  ├─ export_openapi.meta.json
│  │  │  ├─ main.data.json
│  │  │  ├─ main.meta.json
│  │  │  ├─ models.data.json
│  │  │  ├─ models.meta.json
│  │  │  ├─ routers
│  │  │  │  ├─ __init__.data.json
│  │  │  │  ├─ __init__.meta.json
│  │  │  │  ├─ users.data.json
│  │  │  │  └─ users.meta.json
│  │  │  ├─ schemas.data.json
│  │  │  └─ schemas.meta.json
│  │  ├─ apps
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  └─ api
│  │  │     ├─ __init__.data.json
│  │  │     ├─ __init__.meta.json
│  │  │     ├─ main.data.json
│  │  │     └─ main.meta.json
│  │  ├─ ast.data.json
│  │  ├─ ast.meta.json
│  │  ├─ base64.data.json
│  │  ├─ base64.meta.json
│  │  ├─ builtins.data.json
│  │  ├─ builtins.meta.json
│  │  ├─ codecs.data.json
│  │  ├─ codecs.meta.json
│  │  ├─ collections
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  ├─ abc.data.json
│  │  │  └─ abc.meta.json
│  │  ├─ colorsys.data.json
│  │  ├─ colorsys.meta.json
│  │  ├─ configparser.data.json
│  │  ├─ configparser.meta.json
│  │  ├─ contextlib.data.json
│  │  ├─ contextlib.meta.json
│  │  ├─ contextvars.data.json
│  │  ├─ contextvars.meta.json
│  │  ├─ copy.data.json
│  │  ├─ copy.meta.json
│  │  ├─ dataclasses.data.json
│  │  ├─ dataclasses.meta.json
│  │  ├─ datetime.data.json
│  │  ├─ datetime.meta.json
│  │  ├─ decimal.data.json
│  │  ├─ decimal.meta.json
│  │  ├─ dis.data.json
│  │  ├─ dis.meta.json
│  │  ├─ email
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  ├─ _policybase.data.json
│  │  │  ├─ _policybase.meta.json
│  │  │  ├─ charset.data.json
│  │  │  ├─ charset.meta.json
│  │  │  ├─ contentmanager.data.json
│  │  │  ├─ contentmanager.meta.json
│  │  │  ├─ errors.data.json
│  │  │  ├─ errors.meta.json
│  │  │  ├─ header.data.json
│  │  │  ├─ header.meta.json
│  │  │  ├─ message.data.json
│  │  │  ├─ message.meta.json
│  │  │  ├─ policy.data.json
│  │  │  └─ policy.meta.json
│  │  ├─ enum.data.json
│  │  ├─ enum.meta.json
│  │  ├─ fractions.data.json
│  │  ├─ fractions.meta.json
│  │  ├─ functools.data.json
│  │  ├─ functools.meta.json
│  │  ├─ genericpath.data.json
│  │  ├─ genericpath.meta.json
│  │  ├─ inspect.data.json
│  │  ├─ inspect.meta.json
│  │  ├─ io.data.json
│  │  ├─ io.meta.json
│  │  ├─ ipaddress.data.json
│  │  ├─ ipaddress.meta.json
│  │  ├─ itertools.data.json
│  │  ├─ itertools.meta.json
│  │  ├─ json
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  ├─ decoder.data.json
│  │  │  ├─ decoder.meta.json
│  │  │  ├─ encoder.data.json
│  │  │  └─ encoder.meta.json
│  │  ├─ keyword.data.json
│  │  ├─ keyword.meta.json
│  │  ├─ logging
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  ├─ config.data.json
│  │  │  └─ config.meta.json
│  │  ├─ math.data.json
│  │  ├─ math.meta.json
│  │  ├─ numbers.data.json
│  │  ├─ numbers.meta.json
│  │  ├─ opcode.data.json
│  │  ├─ opcode.meta.json
│  │  ├─ operator.data.json
│  │  ├─ operator.meta.json
│  │  ├─ os
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  ├─ path.data.json
│  │  │  └─ path.meta.json
│  │  ├─ pathlib.data.json
│  │  ├─ pathlib.meta.json
│  │  ├─ pickle.data.json
│  │  ├─ pickle.meta.json
│  │  ├─ posixpath.data.json
│  │  ├─ posixpath.meta.json
│  │  ├─ pydantic
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  ├─ _internal
│  │  │  │  ├─ __init__.data.json
│  │  │  │  ├─ __init__.meta.json
│  │  │  │  ├─ _config.data.json
│  │  │  │  ├─ _config.meta.json
│  │  │  │  ├─ _core_metadata.data.json
│  │  │  │  ├─ _core_metadata.meta.json
│  │  │  │  ├─ _core_utils.data.json
│  │  │  │  ├─ _core_utils.meta.json
│  │  │  │  ├─ _dataclasses.data.json
│  │  │  │  ├─ _dataclasses.meta.json
│  │  │  │  ├─ _decorators.data.json
│  │  │  │  ├─ _decorators.meta.json
│  │  │  │  ├─ _decorators_v1.data.json
│  │  │  │  ├─ _decorators_v1.meta.json
│  │  │  │  ├─ _discriminated_union.data.json
│  │  │  │  ├─ _discriminated_union.meta.json
│  │  │  │  ├─ _docs_extraction.data.json
│  │  │  │  ├─ _docs_extraction.meta.json
│  │  │  │  ├─ _fields.data.json
│  │  │  │  ├─ _fields.meta.json
│  │  │  │  ├─ _forward_ref.data.json
│  │  │  │  ├─ _forward_ref.meta.json
│  │  │  │  ├─ _generate_schema.data.json
│  │  │  │  ├─ _generate_schema.meta.json
│  │  │  │  ├─ _generics.data.json
│  │  │  │  ├─ _generics.meta.json
│  │  │  │  ├─ _import_utils.data.json
│  │  │  │  ├─ _import_utils.meta.json
│  │  │  │  ├─ _internal_dataclass.data.json
│  │  │  │  ├─ _internal_dataclass.meta.json
│  │  │  │  ├─ _known_annotated_metadata.data.json
│  │  │  │  ├─ _known_annotated_metadata.meta.json
│  │  │  │  ├─ _mock_val_ser.data.json
│  │  │  │  ├─ _mock_val_ser.meta.json
│  │  │  │  ├─ _model_construction.data.json
│  │  │  │  ├─ _model_construction.meta.json
│  │  │  │  ├─ _namespace_utils.data.json
│  │  │  │  ├─ _namespace_utils.meta.json
│  │  │  │  ├─ _repr.data.json
│  │  │  │  ├─ _repr.meta.json
│  │  │  │  ├─ _schema_gather.data.json
│  │  │  │  ├─ _schema_gather.meta.json
│  │  │  │  ├─ _schema_generation_shared.data.json
│  │  │  │  ├─ _schema_generation_shared.meta.json
│  │  │  │  ├─ _serializers.data.json
│  │  │  │  ├─ _serializers.meta.json
│  │  │  │  ├─ _signature.data.json
│  │  │  │  ├─ _signature.meta.json
│  │  │  │  ├─ _typing_extra.data.json
│  │  │  │  ├─ _typing_extra.meta.json
│  │  │  │  ├─ _utils.data.json
│  │  │  │  ├─ _utils.meta.json
│  │  │  │  ├─ _validate_call.data.json
│  │  │  │  ├─ _validate_call.meta.json
│  │  │  │  ├─ _validators.data.json
│  │  │  │  └─ _validators.meta.json
│  │  │  ├─ _migration.data.json
│  │  │  ├─ _migration.meta.json
│  │  │  ├─ aliases.data.json
│  │  │  ├─ aliases.meta.json
│  │  │  ├─ annotated_handlers.data.json
│  │  │  ├─ annotated_handlers.meta.json
│  │  │  ├─ color.data.json
│  │  │  ├─ color.meta.json
│  │  │  ├─ config.data.json
│  │  │  ├─ config.meta.json
│  │  │  ├─ dataclasses.data.json
│  │  │  ├─ dataclasses.meta.json
│  │  │  ├─ deprecated
│  │  │  │  ├─ __init__.data.json
│  │  │  │  ├─ __init__.meta.json
│  │  │  │  ├─ class_validators.data.json
│  │  │  │  ├─ class_validators.meta.json
│  │  │  │  ├─ config.data.json
│  │  │  │  ├─ config.meta.json
│  │  │  │  ├─ copy_internals.data.json
│  │  │  │  ├─ copy_internals.meta.json
│  │  │  │  ├─ json.data.json
│  │  │  │  ├─ json.meta.json
│  │  │  │  ├─ parse.data.json
│  │  │  │  ├─ parse.meta.json
│  │  │  │  ├─ tools.data.json
│  │  │  │  └─ tools.meta.json
│  │  │  ├─ errors.data.json
│  │  │  ├─ errors.meta.json
│  │  │  ├─ fields.data.json
│  │  │  ├─ fields.meta.json
│  │  │  ├─ functional_serializers.data.json
│  │  │  ├─ functional_serializers.meta.json
│  │  │  ├─ functional_validators.data.json
│  │  │  ├─ functional_validators.meta.json
│  │  │  ├─ json_schema.data.json
│  │  │  ├─ json_schema.meta.json
│  │  │  ├─ main.data.json
│  │  │  ├─ main.meta.json
│  │  │  ├─ networks.data.json
│  │  │  ├─ networks.meta.json
│  │  │  ├─ plugin
│  │  │  │  ├─ __init__.data.json
│  │  │  │  ├─ __init__.meta.json
│  │  │  │  ├─ _schema_validator.data.json
│  │  │  │  └─ _schema_validator.meta.json
│  │  │  ├─ root_model.data.json
│  │  │  ├─ root_model.meta.json
│  │  │  ├─ type_adapter.data.json
│  │  │  ├─ type_adapter.meta.json
│  │  │  ├─ types.data.json
│  │  │  ├─ types.meta.json
│  │  │  ├─ v1
│  │  │  │  ├─ __init__.data.json
│  │  │  │  ├─ __init__.meta.json
│  │  │  │  ├─ annotated_types.data.json
│  │  │  │  ├─ annotated_types.meta.json
│  │  │  │  ├─ class_validators.data.json
│  │  │  │  ├─ class_validators.meta.json
│  │  │  │  ├─ color.data.json
│  │  │  │  ├─ color.meta.json
│  │  │  │  ├─ config.data.json
│  │  │  │  ├─ config.meta.json
│  │  │  │  ├─ dataclasses.data.json
│  │  │  │  ├─ dataclasses.meta.json
│  │  │  │  ├─ datetime_parse.data.json
│  │  │  │  ├─ datetime_parse.meta.json
│  │  │  │  ├─ decorator.data.json
│  │  │  │  ├─ decorator.meta.json
│  │  │  │  ├─ env_settings.data.json
│  │  │  │  ├─ env_settings.meta.json
│  │  │  │  ├─ error_wrappers.data.json
│  │  │  │  ├─ error_wrappers.meta.json
│  │  │  │  ├─ errors.data.json
│  │  │  │  ├─ errors.meta.json
│  │  │  │  ├─ fields.data.json
│  │  │  │  ├─ fields.meta.json
│  │  │  │  ├─ json.data.json
│  │  │  │  ├─ json.meta.json
│  │  │  │  ├─ main.data.json
│  │  │  │  ├─ main.meta.json
│  │  │  │  ├─ networks.data.json
│  │  │  │  ├─ networks.meta.json
│  │  │  │  ├─ parse.data.json
│  │  │  │  ├─ parse.meta.json
│  │  │  │  ├─ schema.data.json
│  │  │  │  ├─ schema.meta.json
│  │  │  │  ├─ tools.data.json
│  │  │  │  ├─ tools.meta.json
│  │  │  │  ├─ types.data.json
│  │  │  │  ├─ types.meta.json
│  │  │  │  ├─ typing.data.json
│  │  │  │  ├─ typing.meta.json
│  │  │  │  ├─ utils.data.json
│  │  │  │  ├─ utils.meta.json
│  │  │  │  ├─ validators.data.json
│  │  │  │  ├─ validators.meta.json
│  │  │  │  ├─ version.data.json
│  │  │  │  └─ version.meta.json
│  │  │  ├─ validate_call_decorator.data.json
│  │  │  ├─ validate_call_decorator.meta.json
│  │  │  ├─ version.data.json
│  │  │  ├─ version.meta.json
│  │  │  ├─ warnings.data.json
│  │  │  └─ warnings.meta.json
│  │  ├─ pydantic_core
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  ├─ _pydantic_core.data.json
│  │  │  ├─ _pydantic_core.meta.json
│  │  │  ├─ core_schema.data.json
│  │  │  └─ core_schema.meta.json
│  │  ├─ re.data.json
│  │  ├─ re.meta.json
│  │  ├─ resource.data.json
│  │  ├─ resource.meta.json
│  │  ├─ scripts
│  │  │  ├─ sql
│  │  │  │  ├─ schema_snapshot.data.json
│  │  │  │  └─ schema_snapshot.meta.json
│  │  │  ├─ sql.data.json
│  │  │  └─ sql.meta.json
│  │  ├─ scripts.data.json
│  │  ├─ scripts.meta.json
│  │  ├─ sre_compile.data.json
│  │  ├─ sre_compile.meta.json
│  │  ├─ sre_constants.data.json
│  │  ├─ sre_constants.meta.json
│  │  ├─ sre_parse.data.json
│  │  ├─ sre_parse.meta.json
│  │  ├─ string.data.json
│  │  ├─ string.meta.json
│  │  ├─ subprocess.data.json
│  │  ├─ subprocess.meta.json
│  │  ├─ sys
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  ├─ _monitoring.data.json
│  │  │  └─ _monitoring.meta.json
│  │  ├─ test_db.data.json
│  │  ├─ test_db.meta.json
│  │  ├─ tests
│  │  │  ├─ conftest.data.json
│  │  │  ├─ conftest.meta.json
│  │  │  ├─ test_users.data.json
│  │  │  ├─ test_users.meta.json
│  │  │  ├─ test_users_extra.data.json
│  │  │  └─ test_users_extra.meta.json
│  │  ├─ tests.data.json
│  │  ├─ tests.meta.json
│  │  ├─ textwrap.data.json
│  │  ├─ textwrap.meta.json
│  │  ├─ threading.data.json
│  │  ├─ threading.meta.json
│  │  ├─ time.data.json
│  │  ├─ time.meta.json
│  │  ├─ types.data.json
│  │  ├─ types.meta.json
│  │  ├─ typing.data.json
│  │  ├─ typing.meta.json
│  │  ├─ typing_extensions.data.json
│  │  ├─ typing_extensions.meta.json
│  │  ├─ typing_inspection
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  ├─ introspection.data.json
│  │  │  ├─ introspection.meta.json
│  │  │  ├─ typing_objects.data.json
│  │  │  └─ typing_objects.meta.json
│  │  ├─ uuid.data.json
│  │  ├─ uuid.meta.json
│  │  ├─ warnings.data.json
│  │  ├─ warnings.meta.json
│  │  ├─ weakref.data.json
│  │  ├─ weakref.meta.json
│  │  ├─ zipfile
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  ├─ _path.data.json
│  │  │  └─ _path.meta.json
│  │  └─ zoneinfo
│  │     ├─ __init__.data.json
│  │     └─ __init__.meta.json
│  └─ CACHEDIR.TAG
├─ .pre-commit-config.yaml
├─ .pytest_cache
│  ├─ CACHEDIR.TAG
│  ├─ README.md
│  └─ v
│     └─ cache
│        ├─ lastfailed
│        └─ nodeids
├─ .ruff_cache
│  ├─ 0.6.9
│  │  ├─ 13044196234816428048
│  │  ├─ 13655890159826208470
│  │  ├─ 15440086879293602839
│  │  ├─ 17338635363283598266
│  │  ├─ 4140081011249886117
│  │  ├─ 6643131234005385388
│  │  └─ 9696191463050372967
│  └─ CACHEDIR.TAG
├─ .secrets.baseline
├─ A.sql
├─ B.sql
├─ Makefile
├─ README.md
├─ README.md.bak.20250923-152955
├─ README.md.bak.20250923-153141
├─ alembic
│  ├─ README
│  ├─ env.py
│  ├─ script.py.mako
│  └─ versions
│     └─ 1157c79168a3_init_users_with_naming.py
├─ alembic.ini
├─ app
│  ├─ __init__.py
│  ├─ db.py
│  ├─ export_openapi.py
│  ├─ main.py
│  ├─ models.py
│  ├─ routers
│  │  ├─ __init__.py
│  │  └─ users.py
│  └─ schemas.py
├─ apps
│  ├─ __init__.py
│  └─ api
│     ├─ __init__.py
│     └─ main.py
├─ bootstrap.sh
├─ contracts
│  ├─ 040_unified_order_model_v1.csv
│  ├─ 040_unified_order_model_v1.md
│  ├─ 170_pdd_inventory_sync.openapi.yaml
│  ├─ 170_pdd_pull_orders.openapi.yaml
│  ├─ 170_pdd_ship_notify.openapi.yaml
│  └─ examples
│     ├─ inventory_sync_conflict.json
│     ├─ pull_orders_replay.json
│     ├─ pull_orders_success.json
│     └─ ship_notify_success.json
├─ db
│  └─ schema.sql
├─ docs
│  └─ 020-implementation
│     └─ README.md
├─ openapi
│  ├─ _current.json
│  └─ v1.json
├─ ops
│  ├─ compose
│  │  ├─ Dockerfile.api
│  │  └─ docker-compose.dev.yml
│  └─ scripts
│     └─ sample.tspl
├─ pyproject.toml
├─ pytest.ini
├─ requirements-dev.txt
├─ requirements.txt
├─ run.sh
├─ scripts
│  ├─ schema_check.sh
│  └─ sql
│     └─ schema_snapshot.py
├─ stop.sh
├─ test_db.py
├─ tests
│  ├─ conftest.py
│  ├─ test_users.py
│  └─ test_users_extra.py
└─ wms-du

```
```
wms-du
├─ .mypy_cache
│  ├─ 3.12
│  │  ├─ @plugins_snapshot.json
│  │  ├─ __future__.data.json
│  │  ├─ __future__.meta.json
│  │  ├─ _ast.data.json
│  │  ├─ _ast.meta.json
│  │  ├─ _codecs.data.json
│  │  ├─ _codecs.meta.json
│  │  ├─ _collections_abc.data.json
│  │  ├─ _collections_abc.meta.json
│  │  ├─ _decimal.data.json
│  │  ├─ _decimal.meta.json
│  │  ├─ _operator.data.json
│  │  ├─ _operator.meta.json
│  │  ├─ _thread.data.json
│  │  ├─ _thread.meta.json
│  │  ├─ _typeshed
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  ├─ importlib.data.json
│  │  │  └─ importlib.meta.json
│  │  ├─ _warnings.data.json
│  │  ├─ _warnings.meta.json
│  │  ├─ _weakref.data.json
│  │  ├─ _weakref.meta.json
│  │  ├─ _weakrefset.data.json
│  │  ├─ _weakrefset.meta.json
│  │  ├─ abc.data.json
│  │  ├─ abc.meta.json
│  │  ├─ alembic
│  │  │  ├─ versions.data.json
│  │  │  └─ versions.meta.json
│  │  ├─ alembic.data.json
│  │  ├─ alembic.meta.json
│  │  ├─ annotated_types
│  │  │  ├─ __init__.data.json
│  │  │  └─ __init__.meta.json
│  │  ├─ app
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  ├─ db.data.json
│  │  │  ├─ db.meta.json
│  │  │  ├─ export_openapi.data.json
│  │  │  ├─ export_openapi.meta.json
│  │  │  ├─ main.data.json
│  │  │  ├─ main.meta.json
│  │  │  ├─ models.data.json
│  │  │  ├─ models.meta.json
│  │  │  ├─ routers
│  │  │  │  ├─ __init__.data.json
│  │  │  │  ├─ __init__.meta.json
│  │  │  │  ├─ users.data.json
│  │  │  │  └─ users.meta.json
│  │  │  ├─ schemas.data.json
│  │  │  └─ schemas.meta.json
│  │  ├─ apps
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  └─ api
│  │  │     ├─ __init__.data.json
│  │  │     ├─ __init__.meta.json
│  │  │     ├─ main.data.json
│  │  │     └─ main.meta.json
│  │  ├─ ast.data.json
│  │  ├─ ast.meta.json
│  │  ├─ base64.data.json
│  │  ├─ base64.meta.json
│  │  ├─ builtins.data.json
│  │  ├─ builtins.meta.json
│  │  ├─ codecs.data.json
│  │  ├─ codecs.meta.json
│  │  ├─ collections
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  ├─ abc.data.json
│  │  │  └─ abc.meta.json
│  │  ├─ colorsys.data.json
│  │  ├─ colorsys.meta.json
│  │  ├─ configparser.data.json
│  │  ├─ configparser.meta.json
│  │  ├─ contextlib.data.json
│  │  ├─ contextlib.meta.json
│  │  ├─ contextvars.data.json
│  │  ├─ contextvars.meta.json
│  │  ├─ copy.data.json
│  │  ├─ copy.meta.json
│  │  ├─ dataclasses.data.json
│  │  ├─ dataclasses.meta.json
│  │  ├─ datetime.data.json
│  │  ├─ datetime.meta.json
│  │  ├─ decimal.data.json
│  │  ├─ decimal.meta.json
│  │  ├─ dis.data.json
│  │  ├─ dis.meta.json
│  │  ├─ email
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  ├─ _policybase.data.json
│  │  │  ├─ _policybase.meta.json
│  │  │  ├─ charset.data.json
│  │  │  ├─ charset.meta.json
│  │  │  ├─ contentmanager.data.json
│  │  │  ├─ contentmanager.meta.json
│  │  │  ├─ errors.data.json
│  │  │  ├─ errors.meta.json
│  │  │  ├─ header.data.json
│  │  │  ├─ header.meta.json
│  │  │  ├─ message.data.json
│  │  │  ├─ message.meta.json
│  │  │  ├─ policy.data.json
│  │  │  └─ policy.meta.json
│  │  ├─ enum.data.json
│  │  ├─ enum.meta.json
│  │  ├─ fractions.data.json
│  │  ├─ fractions.meta.json
│  │  ├─ functools.data.json
│  │  ├─ functools.meta.json
│  │  ├─ genericpath.data.json
│  │  ├─ genericpath.meta.json
│  │  ├─ inspect.data.json
│  │  ├─ inspect.meta.json
│  │  ├─ io.data.json
│  │  ├─ io.meta.json
│  │  ├─ ipaddress.data.json
│  │  ├─ ipaddress.meta.json
│  │  ├─ itertools.data.json
│  │  ├─ itertools.meta.json
│  │  ├─ json
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  ├─ decoder.data.json
│  │  │  ├─ decoder.meta.json
│  │  │  ├─ encoder.data.json
│  │  │  └─ encoder.meta.json
│  │  ├─ keyword.data.json
│  │  ├─ keyword.meta.json
│  │  ├─ logging
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  ├─ config.data.json
│  │  │  └─ config.meta.json
│  │  ├─ math.data.json
│  │  ├─ math.meta.json
│  │  ├─ numbers.data.json
│  │  ├─ numbers.meta.json
│  │  ├─ opcode.data.json
│  │  ├─ opcode.meta.json
│  │  ├─ operator.data.json
│  │  ├─ operator.meta.json
│  │  ├─ os
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  ├─ path.data.json
│  │  │  └─ path.meta.json
│  │  ├─ pathlib.data.json
│  │  ├─ pathlib.meta.json
│  │  ├─ pickle.data.json
│  │  ├─ pickle.meta.json
│  │  ├─ posixpath.data.json
│  │  ├─ posixpath.meta.json
│  │  ├─ pydantic
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  ├─ _internal
│  │  │  │  ├─ __init__.data.json
│  │  │  │  ├─ __init__.meta.json
│  │  │  │  ├─ _config.data.json
│  │  │  │  ├─ _config.meta.json
│  │  │  │  ├─ _core_metadata.data.json
│  │  │  │  ├─ _core_metadata.meta.json
│  │  │  │  ├─ _core_utils.data.json
│  │  │  │  ├─ _core_utils.meta.json
│  │  │  │  ├─ _dataclasses.data.json
│  │  │  │  ├─ _dataclasses.meta.json
│  │  │  │  ├─ _decorators.data.json
│  │  │  │  ├─ _decorators.meta.json
│  │  │  │  ├─ _decorators_v1.data.json
│  │  │  │  ├─ _decorators_v1.meta.json
│  │  │  │  ├─ _discriminated_union.data.json
│  │  │  │  ├─ _discriminated_union.meta.json
│  │  │  │  ├─ _docs_extraction.data.json
│  │  │  │  ├─ _docs_extraction.meta.json
│  │  │  │  ├─ _fields.data.json
│  │  │  │  ├─ _fields.meta.json
│  │  │  │  ├─ _forward_ref.data.json
│  │  │  │  ├─ _forward_ref.meta.json
│  │  │  │  ├─ _generate_schema.data.json
│  │  │  │  ├─ _generate_schema.meta.json
│  │  │  │  ├─ _generics.data.json
│  │  │  │  ├─ _generics.meta.json
│  │  │  │  ├─ _import_utils.data.json
│  │  │  │  ├─ _import_utils.meta.json
│  │  │  │  ├─ _internal_dataclass.data.json
│  │  │  │  ├─ _internal_dataclass.meta.json
│  │  │  │  ├─ _known_annotated_metadata.data.json
│  │  │  │  ├─ _known_annotated_metadata.meta.json
│  │  │  │  ├─ _mock_val_ser.data.json
│  │  │  │  ├─ _mock_val_ser.meta.json
│  │  │  │  ├─ _model_construction.data.json
│  │  │  │  ├─ _model_construction.meta.json
│  │  │  │  ├─ _namespace_utils.data.json
│  │  │  │  ├─ _namespace_utils.meta.json
│  │  │  │  ├─ _repr.data.json
│  │  │  │  ├─ _repr.meta.json
│  │  │  │  ├─ _schema_gather.data.json
│  │  │  │  ├─ _schema_gather.meta.json
│  │  │  │  ├─ _schema_generation_shared.data.json
│  │  │  │  ├─ _schema_generation_shared.meta.json
│  │  │  │  ├─ _serializers.data.json
│  │  │  │  ├─ _serializers.meta.json
│  │  │  │  ├─ _signature.data.json
│  │  │  │  ├─ _signature.meta.json
│  │  │  │  ├─ _typing_extra.data.json
│  │  │  │  ├─ _typing_extra.meta.json
│  │  │  │  ├─ _utils.data.json
│  │  │  │  ├─ _utils.meta.json
│  │  │  │  ├─ _validate_call.data.json
│  │  │  │  ├─ _validate_call.meta.json
│  │  │  │  ├─ _validators.data.json
│  │  │  │  └─ _validators.meta.json
│  │  │  ├─ _migration.data.json
│  │  │  ├─ _migration.meta.json
│  │  │  ├─ aliases.data.json
│  │  │  ├─ aliases.meta.json
│  │  │  ├─ annotated_handlers.data.json
│  │  │  ├─ annotated_handlers.meta.json
│  │  │  ├─ color.data.json
│  │  │  ├─ color.meta.json
│  │  │  ├─ config.data.json
│  │  │  ├─ config.meta.json
│  │  │  ├─ dataclasses.data.json
│  │  │  ├─ dataclasses.meta.json
│  │  │  ├─ deprecated
│  │  │  │  ├─ __init__.data.json
│  │  │  │  ├─ __init__.meta.json
│  │  │  │  ├─ class_validators.data.json
│  │  │  │  ├─ class_validators.meta.json
│  │  │  │  ├─ config.data.json
│  │  │  │  ├─ config.meta.json
│  │  │  │  ├─ copy_internals.data.json
│  │  │  │  ├─ copy_internals.meta.json
│  │  │  │  ├─ json.data.json
│  │  │  │  ├─ json.meta.json
│  │  │  │  ├─ parse.data.json
│  │  │  │  ├─ parse.meta.json
│  │  │  │  ├─ tools.data.json
│  │  │  │  └─ tools.meta.json
│  │  │  ├─ errors.data.json
│  │  │  ├─ errors.meta.json
│  │  │  ├─ fields.data.json
│  │  │  ├─ fields.meta.json
│  │  │  ├─ functional_serializers.data.json
│  │  │  ├─ functional_serializers.meta.json
│  │  │  ├─ functional_validators.data.json
│  │  │  ├─ functional_validators.meta.json
│  │  │  ├─ json_schema.data.json
│  │  │  ├─ json_schema.meta.json
│  │  │  ├─ main.data.json
│  │  │  ├─ main.meta.json
│  │  │  ├─ networks.data.json
│  │  │  ├─ networks.meta.json
│  │  │  ├─ plugin
│  │  │  │  ├─ __init__.data.json
│  │  │  │  ├─ __init__.meta.json
│  │  │  │  ├─ _schema_validator.data.json
│  │  │  │  └─ _schema_validator.meta.json
│  │  │  ├─ root_model.data.json
│  │  │  ├─ root_model.meta.json
│  │  │  ├─ type_adapter.data.json
│  │  │  ├─ type_adapter.meta.json
│  │  │  ├─ types.data.json
│  │  │  ├─ types.meta.json
│  │  │  ├─ v1
│  │  │  │  ├─ __init__.data.json
│  │  │  │  ├─ __init__.meta.json
│  │  │  │  ├─ annotated_types.data.json
│  │  │  │  ├─ annotated_types.meta.json
│  │  │  │  ├─ class_validators.data.json
│  │  │  │  ├─ class_validators.meta.json
│  │  │  │  ├─ color.data.json
│  │  │  │  ├─ color.meta.json
│  │  │  │  ├─ config.data.json
│  │  │  │  ├─ config.meta.json
│  │  │  │  ├─ dataclasses.data.json
│  │  │  │  ├─ dataclasses.meta.json
│  │  │  │  ├─ datetime_parse.data.json
│  │  │  │  ├─ datetime_parse.meta.json
│  │  │  │  ├─ decorator.data.json
│  │  │  │  ├─ decorator.meta.json
│  │  │  │  ├─ env_settings.data.json
│  │  │  │  ├─ env_settings.meta.json
│  │  │  │  ├─ error_wrappers.data.json
│  │  │  │  ├─ error_wrappers.meta.json
│  │  │  │  ├─ errors.data.json
│  │  │  │  ├─ errors.meta.json
│  │  │  │  ├─ fields.data.json
│  │  │  │  ├─ fields.meta.json
│  │  │  │  ├─ json.data.json
│  │  │  │  ├─ json.meta.json
│  │  │  │  ├─ main.data.json
│  │  │  │  ├─ main.meta.json
│  │  │  │  ├─ networks.data.json
│  │  │  │  ├─ networks.meta.json
│  │  │  │  ├─ parse.data.json
│  │  │  │  ├─ parse.meta.json
│  │  │  │  ├─ schema.data.json
│  │  │  │  ├─ schema.meta.json
│  │  │  │  ├─ tools.data.json
│  │  │  │  ├─ tools.meta.json
│  │  │  │  ├─ types.data.json
│  │  │  │  ├─ types.meta.json
│  │  │  │  ├─ typing.data.json
│  │  │  │  ├─ typing.meta.json
│  │  │  │  ├─ utils.data.json
│  │  │  │  ├─ utils.meta.json
│  │  │  │  ├─ validators.data.json
│  │  │  │  ├─ validators.meta.json
│  │  │  │  ├─ version.data.json
│  │  │  │  └─ version.meta.json
│  │  │  ├─ validate_call_decorator.data.json
│  │  │  ├─ validate_call_decorator.meta.json
│  │  │  ├─ version.data.json
│  │  │  ├─ version.meta.json
│  │  │  ├─ warnings.data.json
│  │  │  └─ warnings.meta.json
│  │  ├─ pydantic_core
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  ├─ _pydantic_core.data.json
│  │  │  ├─ _pydantic_core.meta.json
│  │  │  ├─ core_schema.data.json
│  │  │  └─ core_schema.meta.json
│  │  ├─ re.data.json
│  │  ├─ re.meta.json
│  │  ├─ resource.data.json
│  │  ├─ resource.meta.json
│  │  ├─ scripts
│  │  │  ├─ sql
│  │  │  │  ├─ schema_snapshot.data.json
│  │  │  │  └─ schema_snapshot.meta.json
│  │  │  ├─ sql.data.json
│  │  │  └─ sql.meta.json
│  │  ├─ scripts.data.json
│  │  ├─ scripts.meta.json
│  │  ├─ sre_compile.data.json
│  │  ├─ sre_compile.meta.json
│  │  ├─ sre_constants.data.json
│  │  ├─ sre_constants.meta.json
│  │  ├─ sre_parse.data.json
│  │  ├─ sre_parse.meta.json
│  │  ├─ string.data.json
│  │  ├─ string.meta.json
│  │  ├─ subprocess.data.json
│  │  ├─ subprocess.meta.json
│  │  ├─ sys
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  ├─ _monitoring.data.json
│  │  │  └─ _monitoring.meta.json
│  │  ├─ test_db.data.json
│  │  ├─ test_db.meta.json
│  │  ├─ tests
│  │  │  ├─ conftest.data.json
│  │  │  ├─ conftest.meta.json
│  │  │  ├─ test_users.data.json
│  │  │  ├─ test_users.meta.json
│  │  │  ├─ test_users_extra.data.json
│  │  │  └─ test_users_extra.meta.json
│  │  ├─ tests.data.json
│  │  ├─ tests.meta.json
│  │  ├─ textwrap.data.json
│  │  ├─ textwrap.meta.json
│  │  ├─ threading.data.json
│  │  ├─ threading.meta.json
│  │  ├─ time.data.json
│  │  ├─ time.meta.json
│  │  ├─ types.data.json
│  │  ├─ types.meta.json
│  │  ├─ typing.data.json
│  │  ├─ typing.meta.json
│  │  ├─ typing_extensions.data.json
│  │  ├─ typing_extensions.meta.json
│  │  ├─ typing_inspection
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  ├─ introspection.data.json
│  │  │  ├─ introspection.meta.json
│  │  │  ├─ typing_objects.data.json
│  │  │  └─ typing_objects.meta.json
│  │  ├─ uuid.data.json
│  │  ├─ uuid.meta.json
│  │  ├─ warnings.data.json
│  │  ├─ warnings.meta.json
│  │  ├─ weakref.data.json
│  │  ├─ weakref.meta.json
│  │  ├─ zipfile
│  │  │  ├─ __init__.data.json
│  │  │  ├─ __init__.meta.json
│  │  │  ├─ _path.data.json
│  │  │  └─ _path.meta.json
│  │  └─ zoneinfo
│  │     ├─ __init__.data.json
│  │     └─ __init__.meta.json
│  └─ CACHEDIR.TAG
├─ .pre-commit-config.yaml
├─ .pytest_cache
│  ├─ CACHEDIR.TAG
│  ├─ README.md
│  └─ v
│     └─ cache
│        ├─ lastfailed
│        └─ nodeids
├─ .ruff_cache
│  ├─ 0.6.9
│  │  ├─ 13044196234816428048
│  │  ├─ 13655890159826208470
│  │  ├─ 15440086879293602839
│  │  ├─ 17338635363283598266
│  │  ├─ 4140081011249886117
│  │  ├─ 6643131234005385388
│  │  └─ 9696191463050372967
│  └─ CACHEDIR.TAG
├─ .secrets.baseline
├─ A.sql
├─ B.sql
├─ Makefile
├─ README.md
├─ README.md.bak.20250923-152955
├─ README.md.bak.20250923-153141
├─ alembic
│  ├─ README
│  ├─ env.py
│  ├─ script.py.mako
│  └─ versions
│     └─ 1157c79168a3_init_users_with_naming.py
├─ alembic.ini
├─ app
│  ├─ __init__.py
│  ├─ db.py
│  ├─ export_openapi.py
│  ├─ main.py
│  ├─ models.py
│  ├─ routers
│  │  ├─ __init__.py
│  │  └─ users.py
│  └─ schemas.py
├─ apps
│  ├─ __init__.py
│  └─ api
│     ├─ __init__.py
│     └─ main.py
├─ bootstrap.sh
├─ contracts
│  ├─ 040_unified_order_model_v1.csv
│  ├─ 040_unified_order_model_v1.md
│  ├─ 170_pdd_inventory_sync.openapi.yaml
│  ├─ 170_pdd_pull_orders.openapi.yaml
│  ├─ 170_pdd_ship_notify.openapi.yaml
│  └─ examples
│     ├─ inventory_sync_conflict.json
│     ├─ pull_orders_replay.json
│     ├─ pull_orders_success.json
│     └─ ship_notify_success.json
├─ db
│  └─ schema.sql
├─ docs
│  └─ 020-implementation
│     └─ README.md
├─ openapi
│  ├─ _current.json
│  └─ v1.json
├─ ops
│  ├─ compose
│  │  ├─ Dockerfile.api
│  │  └─ docker-compose.dev.yml
│  └─ scripts
│     └─ sample.tspl
├─ pyproject.toml
├─ pytest.ini
├─ requirements-dev.txt
├─ requirements.txt
├─ run.sh
├─ scripts
│  ├─ schema_check.sh
│  └─ sql
│     └─ schema_snapshot.py
├─ stop.sh
├─ test_db.py
├─ tests
│  ├─ conftest.py
│  ├─ test_users.py
│  └─ test_users_extra.py
└─ wms-du

```

---

## Frontend (wms-fe)

本仓库包含前端子工程（Vite + React + MSW）：
- 开发启动：`pnpm dev`
- Mock：MSW（`public/mockServiceWorker.js`），开发环境置 `VITE_USE_MSW=1`
- 入口：`/src/router.tsx`，首页“库存快照 + 三大任务页（Inbound/Putaway/Outbound）+ 工具（Stock/Ledger）”
- Phase2：`/tasks /batches /moves` 壳子与 handlers


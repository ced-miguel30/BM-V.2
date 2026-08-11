"""CLI de despliegue local: prepare, arranque, backup, restore, diagnose.

Uso (desde la raíz del repo, con venv activo)::

    python -m app.core.deploy.cli prepare
    python -m app.core.deploy.cli run-launcher
    python -m app.core.deploy.cli run-streamlit
    python -m app.core.deploy.cli backup
    python -m app.core.deploy.cli verify-backup PATH
    python -m app.core.deploy.cli restore PATH --confirm RESTORE
    python -m app.core.deploy.cli diagnose
    python -m app.core.deploy.cli release-writer
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

from app.core.deploy.config import (
    ENV_ALLOW_OPS,
    DeployConfigError,
    assert_hotel_data_ready,
    ensure_instance_dirs,
    load_deploy_config,
)
from app.core.deploy import ops
from app.core.deploy.runtime import diagnose_lines, prepare_runtime
from app.core.deploy.writer_lock import (
    WriterLockError,
    force_release_if_dead,
    release_writer_lock,
)
from app.core.storage.demo_files import PROJECT_ROOT


def _setup_logging(logs_dir: Path, name: str) -> tuple[Path, list[logging.Handler]]:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{name}.log"
    logger = logging.getLogger("bm.deploy")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    # Cerrar handlers previos (Windows bloquea el .log si queda abierto).
    for h in list(logger.handlers):
        try:
            h.close()
        except OSError:
            pass
        logger.removeHandler(h)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(fh)
    logger.addHandler(sh)
    return log_path, [fh, sh]


def _close_logging(handlers: list[logging.Handler]) -> None:
    logger = logging.getLogger("bm.deploy")
    for h in handlers:
        try:
            h.close()
        except OSError:
            pass
        if h in logger.handlers:
            logger.removeHandler(h)


def _enable_ops_env() -> None:
    os.environ[ENV_ALLOW_OPS] = "1"


def cmd_prepare(_args: argparse.Namespace) -> int:
    cfg = load_deploy_config()
    ensure_instance_dirs(cfg)
    log_path, handlers = _setup_logging(cfg.logs_dir, "prepare")
    try:
        if cfg.is_hotel:
            ops.seed_productive_if_missing(cfg)
            assert_hotel_data_ready(cfg, require_exists=True)
            if cfg.data_file_is_demo():
                raise DeployConfigError("prepare hotel no puede usar el demo.")
        else:
            ensure_instance_dirs(cfg)
        logging.getLogger("bm.deploy").info(
            "prepare_ok profile=%s data=%s log=%s",
            cfg.profile,
            cfg.data_file,
            log_path,
        )
        print(f"OK prepare profile={cfg.profile}")
        print(f"data_file={cfg.data_file}")
        print(f"backups_dir={cfg.backups_dir}")
        print(f"logs_dir={cfg.logs_dir}")
        return 0
    finally:
        _close_logging(handlers)


def cmd_diagnose(_args: argparse.Namespace) -> int:
    cfg = load_deploy_config()
    ensure_instance_dirs(cfg)
    _, handlers = _setup_logging(cfg.logs_dir, "diagnose")
    try:
        for line in diagnose_lines(cfg):
            print(line)
            logging.getLogger("bm.deploy").info(line)
        return 0
    finally:
        _close_logging(handlers)


def cmd_backup(_args: argparse.Namespace) -> int:
    _enable_ops_env()
    cfg = load_deploy_config()
    ensure_instance_dirs(cfg)
    _, handlers = _setup_logging(cfg.logs_dir, "backup")
    try:
        if cfg.is_hotel:
            assert_hotel_data_ready(cfg, require_exists=True)
        path = ops.create_ops_backup(cfg)
        print(f"OK backup={path}")
        return 0
    finally:
        _close_logging(handlers)


def cmd_verify(args: argparse.Namespace) -> int:
    _enable_ops_env()
    cfg = load_deploy_config()
    ensure_instance_dirs(cfg)
    _, handlers = _setup_logging(cfg.logs_dir, "verify_backup")
    try:
        insp = ops.verify_ops_backup(cfg, Path(args.path))
        print(f"OK verify schema={insp.schema_version} fecha={insp.fecha}")
        return 0
    finally:
        _close_logging(handlers)


def cmd_restore(args: argparse.Namespace) -> int:
    _enable_ops_env()
    cfg = load_deploy_config()
    ensure_instance_dirs(cfg)
    _, handlers = _setup_logging(cfg.logs_dir, "restore")
    try:
        if cfg.is_hotel:
            assert_hotel_data_ready(cfg, require_exists=False)
        result = ops.restore_ops_backup(
            cfg, Path(args.path), confirm=args.confirm or ""
        )
        print(f"OK restore estado={result.estado} preventivo={result.backup_preventivo}")
        return 0
    finally:
        _close_logging(handlers)


def cmd_release(args: argparse.Namespace) -> int:
    cfg = load_deploy_config()
    _, handlers = _setup_logging(cfg.logs_dir, "release_writer")
    try:
        if args.force_dead:
            force_release_if_dead(cfg)
            print("OK release (stale)")
            return 0
        release_writer_lock(cfg, only_own=not args.force, force=args.force)
        print("OK release")
        return 0
    finally:
        _close_logging(handlers)


def _run_module(cfg, role: str, module_args: list[str]) -> int:
    from app.core.deploy.writer_lock import acquire_writer_lock, release_writer_lock

    if cfg.is_hotel:
        assert_hotel_data_ready(cfg, require_exists=True)
        acquire_writer_lock(cfg, role=role)
    env = os.environ.copy()
    env["BM_DEMO_FILE"] = str(cfg.data_file)
    env["BM_DEPLOY_PROFILE"] = cfg.profile
    if cfg.instance_root is not None:
        env["BM_INSTANCE_ROOT"] = str(cfg.instance_root)
    env["BM_FLET_VIEW"] = cfg.flet_view
    # El hijo no debe re-adquirir con otro pid sin heredar; marcamos posesión externa.
    env["BM_DEPLOY_WRITER_HELD"] = "1"
    env["BM_DEPLOY_WRITER_ROLE"] = role
    env["BM_DEPLOY_WRITER_PID"] = str(os.getpid())
    try:
        print(
            "AVISO: un único proceso escritor. No abra Flet y Streamlit a la vez "
            "sobre el mismo JSON productivo."
        )
        proc = subprocess.run(
            [sys.executable, "-m", *module_args],
            cwd=str(PROJECT_ROOT),
            env=env,
            check=False,
        )
        return int(proc.returncode)
    finally:
        if cfg.is_hotel:
            try:
                release_writer_lock(cfg, only_own=True)
            except WriterLockError:
                # El candado lo sostiene el padre; only_own por pid del padre.
                from app.core.deploy.writer_lock import lock_path_for

                lock_path_for(cfg.data_file).unlink(missing_ok=True)


def cmd_run_launcher(_args: argparse.Namespace) -> int:
    cfg = load_deploy_config()
    ensure_instance_dirs(cfg)
    _, handlers = _setup_logging(cfg.logs_dir, "launcher")
    try:
        return _run_module(cfg, "flet_launcher", ["app.presentation.flet.main_launcher"])
    finally:
        _close_logging(handlers)


def cmd_run_streamlit(_args: argparse.Namespace) -> int:
    cfg = load_deploy_config()
    ensure_instance_dirs(cfg)
    _, handlers = _setup_logging(cfg.logs_dir, "streamlit")
    try:
        return _run_module(
            cfg,
            "streamlit",
            ["streamlit", "run", "app/main.py", "--server.headless", "true"],
        )
    finally:
        _close_logging(handlers)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m app.core.deploy.cli")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("prepare", help="Crea carpetas y siembra JSON productivo si falta")
    sub.add_parser("diagnose", help="Muestra diagnóstico seguro (sin secretos)")
    sub.add_parser("backup", help="Backup ZIP schema v2 verificable")
    v = sub.add_parser("verify-backup", help="Valida un ZIP de backup")
    v.add_argument("path")
    r = sub.add_parser("restore", help="Restaura un ZIP (confirmación RESTORE)")
    r.add_argument("path")
    r.add_argument("--confirm", default="")
    rel = sub.add_parser("release-writer", help="Libera candado de escritor")
    rel.add_argument("--force", action="store_true")
    rel.add_argument("--force-dead", action="store_true")
    sub.add_parser("run-launcher", help="Arranca launcher Flet (escritor único)")
    sub.add_parser("run-streamlit", help="Arranca Streamlit (escritor único)")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            return cmd_prepare(args)
        if args.command == "diagnose":
            return cmd_diagnose(args)
        if args.command == "backup":
            return cmd_backup(args)
        if args.command == "verify-backup":
            return cmd_verify(args)
        if args.command == "restore":
            return cmd_restore(args)
        if args.command == "release-writer":
            return cmd_release(args)
        if args.command == "run-launcher":
            return cmd_run_launcher(args)
        if args.command == "run-streamlit":
            return cmd_run_streamlit(args)
        parser.error(f"Comando desconocido: {args.command}")
        return 2
    except (DeployConfigError, WriterLockError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR inesperado: {exc}", file=sys.stderr)
        logging.getLogger("bm.deploy").exception("cli_crash")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

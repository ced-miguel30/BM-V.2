"""Alta / cambio de contraseña de usuarios desde el servidor.

    python -m bm.usuarios <login> "<Nombre>" <rol>     (rol: direccion | administracion | recepcion | restaurante)
"""

import getpass
import sys

from bm import db
from bm.passwords import hash_password

ROLES = ("direccion", "administracion", "recepcion", "restaurante")


def guardar(con, login: str, nombre: str, rol: str, password: str) -> None:
    if rol not in ROLES:
        raise ValueError(f"Rol no válido: {rol}")
    login = login.strip().lower()
    existe = con.execute("SELECT id FROM usuarios WHERE login=?", (login,)).fetchone()
    uid = existe["id"] if existe else f"u-{login}"
    con.execute(
        """INSERT INTO usuarios(id, nombre, login, rol, password_hash, activo) VALUES(?,?,?,?,?,1)
           ON CONFLICT(id) DO UPDATE SET nombre=excluded.nombre, rol=excluded.rol,
             password_hash=excluded.password_hash, activo=1""",
        (uid, nombre, login, rol, hash_password(password)),
    )
    con.commit()


if __name__ == "__main__":
    login, nombre, rol = sys.argv[1:4]
    pw = getpass.getpass("Contraseña: ")
    if pw != getpass.getpass("Repite la contraseña: "):
        sys.exit("No coinciden")
    guardar(db.connect(), login, nombre, rol, pw)
    print("Guardado")

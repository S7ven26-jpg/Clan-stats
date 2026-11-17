# Clan Stats: guerras y CWL automáticas (100% gratis)

Plataforma que consulta el API de Clash of Clans cada 20 minutos, guarda cada ataque
y publica un dashboard con las estadísticas de cada jugador, el **MVP de cada guerra,
ronda de CWL y temporada**, y una **tabla de bonos de medallas** lista para copiar.

Todo corre en GitHub (gratis): Actions recolecta, el repositorio guarda los datos y
GitHub Pages muestra la página.

## Instalación (≈15 minutos)

### 1. Crea el repositorio
1. Crea una cuenta en <https://github.com> (gratis) y un repositorio nuevo, **público**
   (Pages gratis requiere repositorio público; los datos son estadísticas públicas del juego).
2. Sube todo el contenido de esta carpeta (incluida la carpeta oculta `.github`).

### 2. Crea tu API key con IP fija (proxy gratuito)
GitHub Actions cambia de IP en cada ejecución y las keys de Supercell están atadas a una IP,
así que se usa el proxy gratuito de RoyaleAPI:

1. Entra a <https://developer.clashofclans.com> → *My Account* → *Create New Key*.
2. En **Allowed IP addresses** pon: `45.79.218.79` (IP del proxy de RoyaleAPI).
3. Copia el token generado.

> La URL del proxy está en `config.json` (`api_base`). Si dejara de funcionar, revisa la
> documentación del proxy de RoyaleAPI (docs.royaleapi.com) por la URL/IP vigentes.

### 3. Guarda la key como secreto
En tu repo: **Settings → Secrets and variables → Actions → New repository secret**
- Name: `COC_API_TOKEN`
- Secret: tu token

### 4. Configura tu clan
Edita `config.json` y cambia `"clan_tag": "#TAGDETUCLAN"` por el tag de tu clan.
**Importante:** el registro de guerra del clan debe estar en **público** (en el juego).

### 5. Activa la página web
**Settings → Pages → Build and deployment → Deploy from a branch →** rama `main`, carpeta `/docs`.
Tu página quedará en `https://TU-USUARIO.github.io/NOMBRE-DEL-REPO/`.

### 6. Primera ejecución
**Actions → "Recolectar datos de Clash of Clans" → Run workflow.** Desde ahí corre solo cada 20 minutos.

## Qué verás en la página
- **Resumen:** MVP de temporada (guerras y CWL), últimos MVPs y rankings (estrellas, ★ netas, 3★ %, destrucción, hit-up, defensa).
- **Jugadores:** tabla ordenable con todas las estadísticas; toca un jugador para ver su historial.
- **Guerras / CWL:** cada guerra y cada ronda con su MVP y el detalle por jugador.
- **Bonos CWL:** medallas sugeridas por jugador, con botón de copiar y descargar CSV.
- **Guía:** explicación de cada estadística.

## Cambiar las reglas
Todo está en `config.json`:
- `mvp_weights`: cuántos puntos vale cada estrella, 3★, % de destrucción, atacar a TH superior y cuánto se penaliza no atacar.
- `cwl_bonus`: medallas por estrella, por 3★, por MVP de ronda, por MVP de temporada, penalización por ataque no usado y mínimo de rondas para ser elegible.

Los cambios se aplican en la siguiente ejecución del colector (o corre el workflow a mano).

## Probar sin API key (demo)
```bash
python3 tools/make_demo.py
python3 -m http.server -d docs 8000
# abre http://localhost:8000/?demo=1
```

## Límites a tener en cuenta
- El API solo entrega la guerra en curso: **el historial empieza el día que se activa el colector**, no hay forma de recuperar guerras anteriores.
- GitHub puede retrasar las ejecuciones programadas unos minutos; no afecta porque las guerras duran horas.
- La temporada de las guerras normales se asigna por el mes en que terminan; la de CWL usa la temporada oficial.
- El MVP de temporada es provisional hasta que termina el mes (guerras) o se juegan las 7 rondas (CWL).

## Estructura
```
config.json                  reglas y tag del clan
collector/collect.py         consulta el API y guarda guerras/CWL en data/
collector/stats.py           calcula MVPs, estadísticas y bonos -> docs/data/stats.json
docs/index.html              dashboard (GitHub Pages)
.github/workflows/collect.yml  automatización cada 20 min
tools/make_demo.py           datos de ejemplo
```

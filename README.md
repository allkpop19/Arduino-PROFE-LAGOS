# Arduino PROFE LAGOS: Kamehouse Sec

Proyecto educativo de control de acceso para una maqueta con Arduino, sensor ultrasónico, servomotor y una página web local en Python.

## Funcionamiento

1. El sensor confirma presencia entre 2 y 10 cm.
2. La página abierta muestra el panel de contraseña.
3. El servidor valida una clave privada y envía la orden por USB.
4. El servo gira a 90° y vuelve a 0° después de 5 segundos.
5. Para repetir el acceso, hay que alejar el objeto al menos a 12 cm y acercarlo otra vez.

## Conexiones

| Componente | Arduino |
| --- | --- |
| Sensor TRIG | 5 |
| Sensor ECHO | 6 |
| Señal del servo | 7 |
| Alimentación | 5V y GND común |

## Instalación en Windows

1. Descarga o clona el repositorio y entra a `kamehouse-sec`.
2. Copia `config.example.json` como `config.json`.
3. Escribe tu propia contraseña en `contrasena`. El archivo de ejemplo trae ese campo vacío. `puerto` puede quedar en `AUTO` o tomar el puerto COM de tu Arduino.
4. Ejecuta `instalar.bat` con Python 3.10 o superior instalado.
5. Carga `arduino/casa/casa.ino` desde el IDE de Arduino. Usa la biblioteca Servo y después cierra el Monitor Serie.
6. Ejecuta `iniciar.bat` y abre <http://127.0.0.1:8000>.

`demo.bat` muestra una simulación de la interfaz sin controlar hardware.

## Archivos

Todo el código del proyecto está en `kamehouse-sec/`: firmware, servidor FastAPI, comunicación serial, almacenamiento SQLite, interfaz, instaladores y pruebas. Lee [las instrucciones completas](kamehouse-sec/LEEME.md) y [las pruebas](kamehouse-sec/PRUEBAS.md).

## Pruebas de software

Dentro de `kamehouse-sec`, prepara las dependencias de desarrollo:

```bash
python -m pip install -r requirements.txt pytest httpx
```

Para ejecutar las pruebas, usa una copia temporal de `config.json` con la contraseña sintética `clave-prueba`. Los tests de configuración usan esa clave de ejemplo. No uses tu base de datos habitual: define `CASA_DATOS` para que apunte a una carpeta temporal antes de importar la aplicación.

```bash
python -m pytest -q tests
node --check static/app.js
node --check static/theme.js
```

La prueba C++ de la lógica del firmware se describe en `PRUEBAS.md`. Node y g++ solo sirven para estas comprobaciones y no son necesarios para ejecutar la página.

## Privacidad

El repositorio excluye configuración privada, base de datos, historial, registros y entornos locales. No publica contraseñas de uso real. `config.example.json` es una plantilla sin clave. Las claves que aparecen en las pruebas son datos sintéticos.

La presentación y los paquetes anteriores no se incluyen porque contienen una contraseña de la instalación original. El código fuente y las instrucciones sí forman parte de esta copia pública.

## Alcance

Maqueta educativa. La confirmación del firmware indica que aceptó la orden, pero no mide la posición física de la puerta. La verificación del conjunto físico depende del cableado, alimentación, sensor y servo de cada instalación.

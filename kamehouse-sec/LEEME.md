# Kamehouse Sec

Página local para tu maqueta: Arduino + sensor ultrasónico + un servo. Se usa en el mismo PC que tiene el USB conectado.

## Actualizar a esta versión

1. Detén el servidor anterior con Ctrl+C.
2. Extrae todo el ZIP en una carpeta nueva.
3. Ejecuta instalar.bat de nuevo: esta versión añade una dependencia para las fechas de Chile.
4. Ejecuta iniciar.bat y abre http://127.0.0.1:8000.
5. Antes de iniciar, copia `config.example.json` como `config.json` y completa `contrasena` con una clave privada. No subas `config.json` al repositorio. La clave sirve para abrir la puerta y entrar a Configuración.

Si tu Arduino ya tiene el último casa.ino de este proyecto, no necesitas cargarlo otra vez para estas mejoras de la página. Conserva tu puerto real en config.json si antes lo habías configurado.

## Funcionamiento de la puerta

- El sensor detecta entre 2 y 10 cm. Se requieren dos lecturas cercanas para confirmar presencia.
- Con la página abierta, la detección muestra el panel de contraseña; no abre la puerta por sí sola.
- Con contraseña correcta, Python envía la orden por USB y espera la confirmación del firmware.
- El Arduino manda el servo a 90° y lo devuelve a 0° cinco segundos después.
- Para otro acceso, hay que alejarse al menos a 12 cm y volver a acercarse.
- El temporizador corre en el Arduino: cierra aunque cierres la página o el servidor, siempre que la placa conserve alimentación.
- La confirmación viene del firmware; no hay un sensor que confirme la posición física del motor.

## Conexiones

Desconecta el USB antes de mover cables.

| Componente | Arduino |
|---|---|
| Sensor TRIG | 5 |
| Sensor ECHO | 6 |
| Sensor VCC | 5V |
| Sensor GND | GND |
| Señal del servo, naranja/amarillo | 7 |
| Alimentación del servo, rojo | 5V |
| Tierra del servo, café/negro | GND |

El peaje no se utiliza. Si el servo provoca temblores o reinicios, revisa su alimentación. Puedes usar una fuente regulada de 5 V para el servo compartiendo GND con Arduino; mientras uses USB, deja el positivo de esa fuente separado del pin 5V de la placa.

## Preparar el Arduino

Abre arduino/casa/casa.ino en el IDE, selecciona tu placa y puerto, y carga el programa. Si falta Servo.h, instala Servo de Arduino desde el administrador de bibliotecas.

Después cierra el Monitor Serie y el Serial Plotter. El firmware y Python se comunican a 115200 baudios.

La constante PRUEBA_SERVO debe quedar en false para uso normal. Puedes ponerla temporalmente en true para que al arrancar pruebe 0° → 90° → 0°. Esa comprobación no usa sensor, contraseña ni página. Luego restaura false y vuelve a cargar.

## Archivos para iniciar

- instalar.bat: crea el entorno de Python e instala requirements.txt. Necesita Internet durante la instalación.
- iniciar.bat: arranca el servidor con el Arduino real. Deja la ventana abierta.
- demo.bat: permite probar sin placa. Muestra claramente «Modo de demostración» y no abre ningún puerto USB.
- config.example.json: plantilla pública sin contraseña.
- config.json: configuración privada creada por cada usuario, excluida de git.
- app.py: servidor, contraseñas, configuración e historial.
- bridge.py: comunicación USB y simulación.
- storage.py: datos persistentes y contraseña protegida con hash.
- static: HTML, diseño, comportamiento de la página y selector de tema.
- tests y PRUEBAS.md: comprobaciones técnicas, no hacen falta para el uso diario.

Necesitas Python 3.10 o superior. Abre la página siempre mediante el servidor; no hagas doble clic en index.html.

## Configuración desde la página

Pulsa **Configuración** arriba e ingresa la contraseña actual.

Puedes:

- Cambiar el nombre de la casa.
- Activar o desactivar los sonidos de apertura, cierre y contraseña incorrecta.
- Usar «Probar sonido» para escuchar un aviso.
- Cambiar la contraseña escribiendo la actual y repitiendo la nueva, de al menos cuatro caracteres.
- Cerrar la sesión de configuración cuando termines.

La sesión dura 15 minutos. Un cambio de contraseña cierra todas las sesiones de configuración. La apertura de la puerta siempre requiere la contraseña, aunque ya tengas una sesión de configuración abierta.

Los sonidos están desactivados al principio. El navegador puede requerir un clic o una tecla antes de reproducirlos. El botón «Probar sonido» funciona como prueba incluso antes de guardar el interruptor.

## Historial y estadísticas

La página muestra:

- Aperturas autorizadas de hoy.
- Intentos de contraseña rechazados hoy, incluidos los de configuración.
- Fecha y hora de la última entrada.
- Historial con tipo, detalle, fecha y hora; filtros por evento y fecha; páginas de 20 registros.

Se registran detecciones, aperturas, cierres, intentos fallidos, conexión y cambios de configuración. Nunca se guarda la contraseña que escribió la persona en el historial.

Las fechas se muestran según America/Santiago. El historial de demostración se mantiene separado del real para que las pruebas no inflen las estadísticas de tu casa. El nombre y la contraseña sí son comunes a ambos modos.

## Dónde se guardan los cambios

Al iniciar se crea **datos/casa.sqlite3** con el historial, nombre, sonido y contraseña en forma de hash. Los cambios siguen ahí al cerrar el navegador o reiniciar el servidor.

Conserva la carpeta **datos** al actualizar el proyecto. El ZIP no trae registros ni datos personales. Para respaldar, detén el servidor y copia toda la carpeta datos a un lugar seguro.

La contraseña privada de config.json se usa solo cuando se crea la base de datos por primera vez. Después cambia la contraseña desde la página. Cambiar config.json y reiniciar no reemplaza una contraseña que ya guardaste.

Si defines CASA_PASSWORD en el entorno, esa contraseña se usa mientras la variable esté activa y el cambio desde la página se deshabilita. CASA_PUERTO permite fijar el puerto y CASA_DATOS permite elegir otra carpeta para los datos.

## Apariencia

Modo claro: fondo blanco, azul y amarillo.

Modo oscuro: fondo negro y escala de grises, incluidos el panel y la ilustración. La elección se guarda en ese navegador.

## Puerto USB y diagnóstico

En config.json puedes cambiar AUTO por el puerto real del IDE:

    {"puerto": "COM3", "contrasena": "TU_CLAVE_PRIVADA"}

Usa COM3 solo si tu placa está realmente en COM3. Reinicia el servidor después de cambiar el puerto.

Los tres indicadores distinguen:

1. **Servidor:** si el navegador puede hablar con la aplicación Python.
2. **USB:** si el puerto está abierto.
3. **Datos del Arduino:** si están llegando mensajes válidos y recientes.

«USB abierto · esperando datos» no significa que se haya quitado el cable. Esta versión conserva el puerto abierto durante silencios y recompone las líneas seriales que llegan fragmentadas. Solo intenta reconectar cuando falla el acceso al puerto.

## Si algo falla

- Cierra otros servidores, el Monitor Serie y el Serial Plotter. Deja una sola aplicación usando el COM.
- No uses --reload ni varios --workers: pueden competir por el USB.
- Si indica datos inválidos, carga el casa.ino de este proyecto, no el antiguo que abría automáticamente con el sensor.
- Si el servidor está en línea pero el USB no, revisa puerto, cable y controlador.
- Si se reinicia al mover el motor, desconecta el USB, retira el servo y prueba Arduino + sensor. Si se estabiliza, revisa alimentación, servo y cableado.
- Si la página parece vieja, recarga con Ctrl+F5.
- Si usas demo.bat, el motor nunca se moverá.
- Si el puerto 8000 está ocupado, cierra el otro servidor o usa 8001.
- Si aparece un aviso de que no pudo guardarse el historial, revisa espacio libre y permisos de la carpeta datos.

## Comandos manuales

Desde la carpeta del proyecto:

    python -m pip install -r requirements.txt
    python -m uvicorn app:app --host 127.0.0.1 --port 8000

Con el entorno que crea instalar.bat:

    .venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000

## Alcance

Proyecto educativo para una maqueta. Mantén la página y el servidor abiertos mientras lo uses. No tiene realimentación del servo ni protección antiatrapamiento para una puerta de tamaño real.

Las pruebas de software no sustituyen revisar el cableado, alimentación y funcionamiento con tu placa.

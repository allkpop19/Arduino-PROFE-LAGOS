# Pruebas técnicas

Desde la carpeta del proyecto, en un entorno con Python y las dependencias instaladas:

```bash
python -m pip install pytest httpx
python -m pytest -q tests
node --check static/app.js
node --check static/theme.js
```

Node solo se utiliza para verificar la sintaxis de JavaScript; no hace falta para ejecutar la aplicación.

Para verificar el firmware con g++ (simula reloj, sensor, serial y servo; no requiere una placa):

```bash
g++ -std=c++11 -I tests/firmware -include tests/firmware/Arduino.h tests/firmware/test_firmware.cpp -o firmware_test
./firmware_test
```

Las pruebas cubren:

- Presencia por sí sola no abre la puerta.
- Contraseña incorrecta, token obsoleto y ausencia de persona rechazan la apertura.
- Bloqueo de 30 segundos tras cinco errores.
- Confirmación serial obligatoria; desconexión y rechazo no se muestran como éxito.
- No existe bypass de simulación en modo real.
- No se expone `config.json` y se rechazan solicitudes desde otros sitios.
- Cierre a los 5 segundos, duplicados sin extender el plazo y rearme al alejarse.
- Entrada serial inválida y desbordada no abre la puerta.

El stub C++ prueba la lógica del mismo archivo `.ino`, pero no sustituye compilarlo para tu placa con el IDE de Arduino. Falta la prueba física de USB, alimentación, sensor y servo en tu equipo.

## Resultado en la preparación del proyecto

19 pruebas del servidor, persistencia, configuración y comunicación serial aprobadas; prueba de lógica C++ del firmware aprobada; sintaxis de los dos archivos JavaScript verificada con Node. La prueba del firmware incluye rechazo a 15 cm y a 10,29 cm, detección a 9,95 cm y retirada de presencia a partir de 12 cm, además del cierre a los 5 segundos.

Se revisó la interfaz en navegador con datos de prueba: fondo blanco con azul y amarillo, panel de contraseña, modo oscuro en escala de grises y conservación del tema al recargar. La vista de prueba usa estados de ejemplo; la comunicación física USB y el servo siguen pendientes de comprobar en el PC del usuario.

La corrección de estabilidad añade cuatro pruebas: arranque retrasado de ocho segundos sin reabrir el COM; reconstrucción de JSON fragmentado y recuperación tras ruido; reconexión ante errores USB reales; y bloqueo de apertura con datos antiguos aunque el puerto siga abierto.

La configuración y persistencia añaden seis pruebas: contraseña inicial TU_CLAVE_PRIVADA y acceso protegido a configuración; guardado de nombre, sonido y contraseña tras reiniciar; revocación de sesiones al cambiar contraseña; historial y estadísticas separados por modo real/demostración; filtros por tipo y fecha de Chile con paginación; y caducidad de sesión, hash de contraseña y bloqueo de intentos fallidos.

La revisión visual de esta versión usa una vista estática con respuestas obtenidas del simulador: se comprobaron la tabla, estadísticas, diagnóstico, configuración y tema oscuro. La lógica de guardado y autenticación se verificó con el servidor real a través de TestClient. El control de sonido se ejercitó en el navegador; la reproducción audible depende de los permisos y la salida de audio del equipo del usuario.

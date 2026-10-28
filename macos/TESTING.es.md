# Pruebas de Monitorize en macOS Intel

Versión preliminar. Requiere un Mac Intel con macOS 12 o posterior.
Sunshine no está incluido. La API privada de pantallas puede variar según macOS.

## Instalar

1. Descarga `Monitorize-macos-intel.zip` de la release y descomprímelo.
2. Mueve `Monitorize.app` a Aplicaciones. No hace falta instalar Python.
3. Es una compilación de prueba sin notarización de Apple. Si macOS bloquea su
   apertura, utiliza la opción «Abrir igualmente» en Privacidad y seguridad solo
   después de verificar su procedencia. No desactives Gatekeeper ni SIP.
4. Abre la aplicación dentro de una sesión gráfica local.

Comprueba la integridad de la descarga con `shasum -a 256 Monitorize-macos-intel.zip`
y compara el resultado con `SHA256SUMS.txt` publicado en la misma release.

## Primera prueba: pantallas sin streaming

1. En Display 1 elige «Create virtual display», 1920 × 1080, 60 Hz y pulsa Start.
2. Confirma que aparece una pantalla adicional en Ajustes del Sistema → Pantallas.
3. Arrástrala a una posición útil y mueve una ventana a ella.
4. Repite en Display 2 con 1280 × 720, 60 Hz.
5. Detén cada pantalla por separado. La otra debe seguir activa.
6. Cierra Monitorize: sus pantallas deben desaparecer sin afectar a los monitores físicos.

No cambies tu pantalla principal ni pruebes a desconectar el único monitor físico
hasta haber confirmado el funcionamiento básico.

## Segunda prueba: Moonlight

1. Instala Sunshine para macOS Intel con selección por ID CoreGraphics
   (consulta la compatibilidad en el README). Inícialo una vez para otorgarle
   permisos de Grabación de pantalla y Accesibilidad; detén esa instancia antes
   de usar los perfiles de Monitorize si ocupa sus puertos.
2. Crea la pantalla 1 y pulsa Start Sunshine.
3. Abre Pair / Sunshine settings y configura las credenciales locales.
4. En Moonlight añade la IP del Mac; empareja usando el PIN y abre Desktop.
5. Confirma en el log qué display captura Sunshine y verifica que ves la pantalla correcta.
6. Para la segunda sesión añade `IP_DEL_MAC:49089`. Repite el emparejamiento.
7. Prueba ratón, teclado, desconexión/reconexión y cierre de Monitorize.

Las interfaces web son locales: `https://localhost:47990` y
`https://localhost:49090`. Sunshine usa un certificado local autofirmado.
La aplicación no desactiva la comprobación TLS.

## Si falla

Indica modelo de Mac, versión de macOS, nombre de la release y el paso exacto.
Copia el mensaje mostrado por Monitorize y los errores relevantes de
`~/Library/Application Support/Monitorize/sunshine-1/sunshine.log`
(o `sunshine-2`). No compartas contraseñas, claves ni archivos de credenciales.
Para obtener mensajes de inicio, ejecuta desde Terminal:

```sh
/Applications/Monitorize.app/Contents/MacOS/Monitorize
```

La compilación y las pruebas automáticas no prueban el streaming real: se necesita
esta prueba manual en el Mac con Moonlight.

import { useEffect, useRef, useState } from 'react';
import { Alert } from '@mantine/core';

// Lector de códigos de barras con la cámara del móvil.
// Chrome en Android trae su propio lector; en iPhone (y donde no lo haya) se usa uno incluido en BM (zxing),
// que se descarga del propio servidor y queda guardado: también funciona sin cobertura.
// La cámara solo se permite con https (o en localhost). Un lector USB/Bluetooth funciona siempre: escribe en el buscador.

type Detector = { detect: (v: HTMLVideoElement) => Promise<{ rawValue: string }[]> };
const FORMATOS = ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128', 'code_39', 'itf', 'qr_code'];

async function crearDetector(): Promise<Detector> {
  const Nativo = (window as any).BarcodeDetector;
  if (Nativo && (await Nativo.getSupportedFormats?.().catch(() => []))?.includes('ean_13')) return new Nativo({ formats: FORMATOS });
  const [{ BarcodeDetector, setZXingModuleOverrides }, { default: wasm }] = await Promise.all([
    import('barcode-detector/ponyfill'), import('zxing-wasm/reader/zxing_reader.wasm?url'),
  ]);
  setZXingModuleOverrides({ locateFile: (f: string, prefijo: string) => (f.endsWith('.wasm') ? wasm : prefijo + f) });
  return new BarcodeDetector({ formats: FORMATOS as any });
}

/** Descarga el lector al abrir el recuento (con cobertura), para tenerlo guardado si luego se cuenta sin ella. */
export const prepararLector = () => { crearDetector().catch(() => null); };

export const hayCamara = () => window.isSecureContext && !!navigator.mediaDevices?.getUserMedia;

// Aviso al leer: vibración (Android) y pitido corto.
let audio: AudioContext | null = null;
function pitido() {
  navigator.vibrate?.(80);
  try {
    audio ??= new AudioContext();
    const o = audio.createOscillator();
    o.frequency.value = 1400;
    o.connect(audio.destination);
    o.start(); o.stop(audio.currentTime + 0.08);
  } catch { /* sin sonido */ }
}

/** Vídeo de la cámara trasera. Mientras `activa`, cada código leído llama a `leido` (el padre la pausa para pedir la cantidad). */
export function Camara({ activa, leido }: { activa: boolean; leido: (codigo: string) => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const actual = useRef({ activa, leido });
  actual.current = { activa, leido };
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let parar = false;
    let flujo: MediaStream | null = null;
    (async () => {
      try {
        const detector = await crearDetector();
        flujo = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
        const v = video.current;
        if (parar || !v) return;
        v.srcObject = flujo;
        await v.play();
        while (!parar) {
          if (actual.current.activa && v.readyState >= 2) {
            const r = await detector.detect(v).catch(() => []);
            if (r.length && actual.current.activa && !parar) { pitido(); actual.current.leido(r[0].rawValue); }
          }
          await new Promise((ok) => setTimeout(ok, 200));
        }
      } catch (e) {
        setError((e as Error)?.name === 'NotAllowedError'
          ? 'El navegador no deja usar la cámara. Permítela en los ajustes del navegador para esta página.'
          : 'No se pudo abrir la cámara.');
      } finally {
        if (parar) flujo?.getTracks().forEach((t) => t.stop());
      }
    })();
    return () => { parar = true; flujo?.getTracks().forEach((t) => t.stop()); };
  }, []);

  if (error) return <Alert color="red" variant="light">{error}</Alert>;
  return (
    <div style={{ position: 'relative' }}>
      <video ref={video} playsInline muted style={{ width: '100%', maxHeight: '38vh', objectFit: 'cover', borderRadius: 12, background: '#000', display: 'block', opacity: activa ? 1 : 0.35 }} />
      {activa && <div style={{ position: 'absolute', left: '10%', right: '10%', top: '50%', height: 2, background: 'rgba(255,60,60,.9)', boxShadow: '0 0 8px red' }} />}
    </div>
  );
}

import { useEffect, useRef } from 'react';
import { Modal, Text } from '@mantine/core';

// Lector de códigos de barras con la cámara (BarcodeDetector del navegador: Chrome en Android, sí; en Windows o iPhone, no).
// La cámara solo se permite con HTTPS o en localhost. Un lector USB/Bluetooth funciona siempre: escribe en el buscador.
declare global {
  interface Window { BarcodeDetector?: new (o: { formats: string[] }) => { detect: (v: HTMLVideoElement) => Promise<{ rawValue: string }[]> } }
}

export const hayCamara = () => !!window.BarcodeDetector && window.isSecureContext && !!navigator.mediaDevices?.getUserMedia;

export function Escaner({ abierto, cerrar, leido }: { abierto: boolean; cerrar: () => void; leido: (codigo: string) => void }) {
  const video = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    if (!abierto || !window.BarcodeDetector) return;
    let parar = false;
    let flujo: MediaStream | null = null;
    const detector = new window.BarcodeDetector({ formats: ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128', 'code_39'] });
    navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } }).then(async (s) => {
      flujo = s;
      if (!video.current) return;
      video.current.srcObject = s;
      await video.current.play();
      while (!parar) {
        const r = await detector.detect(video.current).catch(() => []);
        if (r.length) { parar = true; leido(r[0].rawValue); cerrar(); break; }
        await new Promise((ok) => setTimeout(ok, 250));
      }
    }).catch(() => cerrar());
    return () => { parar = true; flujo?.getTracks().forEach((t) => t.stop()); };
  }, [abierto]);
  return (
    <Modal opened={abierto} onClose={cerrar} title="Escanear código" centered>
      <video ref={video} playsInline muted style={{ width: '100%', borderRadius: 8, background: '#000' }} />
      <Text size="sm" c="dimmed" mt="xs">Apunta al código de barras del envase.</Text>
    </Modal>
  );
}

/**
 * Barcode Scanner Module
 * Használja a natív Barcode Detection API-t ha elérhető (Chrome/Android),
 * egyébként fallback html5-qrcode-ra.
 */

class BarcodeScanner {
    constructor(containerId, onDetected, options = {}) {
        this.containerId = containerId;
        this.onDetected = onDetected;
        this.options = {
            fps: 15,
            qrbox: { width: 280, height: 150 },
            aspectRatio: 1.777,
            focusMode: 'continuous',
            ...options
        };
        
        this.isScanning = false;
        this.stream = null;
        this.videoElement = null;
        this.barcodeDetector = null;
        this.html5QrCode = null;
        this.scanInterval = null;
        this.lastDetected = null;
        this.lastDetectedTime = 0;
        this.debounceMs = 1500; // Ugyanazt a kódot 1.5mp-en belül ne olvassa újra
        
        // Ellenőrizzük a Barcode Detection API támogatását
        this.useNativeAPI = 'BarcodeDetector' in window;
        
        console.log('BarcodeScanner initialized, native API:', this.useNativeAPI);
    }
    
    async start() {
        if (this.isScanning) return;
        
        try {
            if (this.useNativeAPI) {
                await this.startNative();
            } else {
                await this.startHtml5QrCode();
            }
            this.isScanning = true;
        } catch (err) {
            console.error('Kamera indítási hiba:', err);
            throw err;
        }
    }
    
    async startNative() {
        const container = document.getElementById(this.containerId);
        container.innerHTML = '<video id="barcode-video" playsinline autoplay muted style="width:100%;border-radius:8px;"></video>';
        
        this.videoElement = document.getElementById('barcode-video');
        
        // Kamera indítása optimális beállításokkal
        const constraints = {
            video: {
                facingMode: 'environment',
                width: { ideal: 1280 },
                height: { ideal: 720 },
                focusMode: 'continuous',
                exposureMode: 'continuous',
                whiteBalanceMode: 'continuous'
            }
        };
        
        // Próbáljuk meg a legjobb beállításokat
        try {
            this.stream = await navigator.mediaDevices.getUserMedia(constraints);
        } catch (e) {
            // Fallback egyszerűbb beállításokkal
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: 'environment' }
            });
        }
        
        this.videoElement.srcObject = this.stream;
        
        // Várjuk meg, hogy a videó elinduljon
        await new Promise((resolve) => {
            this.videoElement.onloadedmetadata = () => {
                this.videoElement.play();
                resolve();
            };
        });
        
        // Barcode Detector inicializálása
        this.barcodeDetector = new BarcodeDetector({
            formats: ['ean_13', 'ean_8', 'code_128', 'code_39', 'code_93', 'upc_a', 'upc_e', 'itf', 'qr_code']
        });
        
        // Folyamatos szkennelés
        this.scanInterval = setInterval(() => this.detectFrame(), 1000 / this.options.fps);
    }
    
    async detectFrame() {
        if (!this.videoElement || !this.barcodeDetector) return;
        
        try {
            const barcodes = await this.barcodeDetector.detect(this.videoElement);
            
            if (barcodes.length > 0) {
                const barcode = barcodes[0];
                const now = Date.now();
                
                // Debounce - ne olvassa újra ugyanazt a kódot
                if (barcode.rawValue !== this.lastDetected || 
                    now - this.lastDetectedTime > this.debounceMs) {
                    
                    this.lastDetected = barcode.rawValue;
                    this.lastDetectedTime = now;
                    
                    // Vibráció visszajelzés (ha támogatott)
                    if ('vibrate' in navigator) {
                        navigator.vibrate(100);
                    }
                    
                    console.log('Barcode detected:', barcode.rawValue, barcode.format);
                    this.onDetected(barcode.rawValue, barcode.format);
                }
            }
        } catch (err) {
            // Csendben hagyjuk, a következő frame-en újra próbálkozunk
        }
    }
    
    async startHtml5QrCode() {
        // Fallback html5-qrcode-ra
        if (typeof Html5Qrcode === 'undefined') {
            throw new Error('Html5Qrcode library not loaded');
        }
        
        this.html5QrCode = new Html5Qrcode(this.containerId);
        
        const config = {
            fps: this.options.fps,
            qrbox: this.options.qrbox,
            aspectRatio: this.options.aspectRatio,
            formatsToSupport: [
                Html5QrcodeSupportedFormats.EAN_13,
                Html5QrcodeSupportedFormats.EAN_8,
                Html5QrcodeSupportedFormats.CODE_128,
                Html5QrcodeSupportedFormats.CODE_39,
                Html5QrcodeSupportedFormats.UPC_A,
                Html5QrcodeSupportedFormats.UPC_E,
                Html5QrcodeSupportedFormats.QR_CODE
            ]
        };
        
        await this.html5QrCode.start(
            { facingMode: "environment" },
            config,
            (decodedText, decodedResult) => {
                const now = Date.now();
                
                // Debounce
                if (decodedText !== this.lastDetected || 
                    now - this.lastDetectedTime > this.debounceMs) {
                    
                    this.lastDetected = decodedText;
                    this.lastDetectedTime = now;
                    
                    if ('vibrate' in navigator) {
                        navigator.vibrate(100);
                    }
                    
                    this.onDetected(decodedText, decodedResult?.result?.format?.formatName);
                }
            },
            (errorMessage) => {
                // Csendben hagyjuk a sikertelen olvasásokat
            }
        );
    }
    
    async stop() {
        if (!this.isScanning) return;
        
        try {
            if (this.useNativeAPI) {
                if (this.scanInterval) {
                    clearInterval(this.scanInterval);
                    this.scanInterval = null;
                }
                if (this.stream) {
                    this.stream.getTracks().forEach(track => track.stop());
                    this.stream = null;
                }
                if (this.videoElement) {
                    this.videoElement.srcObject = null;
                }
            } else if (this.html5QrCode && this.html5QrCode.isScanning) {
                await this.html5QrCode.stop();
            }
        } catch (err) {
            console.error('Kamera leállítási hiba:', err);
        }
        
        this.isScanning = false;
        this.lastDetected = null;
        this.lastDetectedTime = 0;
    }
    
    // Újraindítás (pl. automata váltás után)
    async restart() {
        await this.stop();
        await this.start();
    }
    
    // Ellenőrzés, hogy fut-e
    isRunning() {
        return this.isScanning;
    }
    
    // Statikus metódus a támogatottság ellenőrzésére
    static isSupported() {
        return 'mediaDevices' in navigator && 'getUserMedia' in navigator.mediaDevices;
    }
    
    static hasNativeSupport() {
        return 'BarcodeDetector' in window;
    }
    
    static async getSupportedFormats() {
        if ('BarcodeDetector' in window) {
            return await BarcodeDetector.getSupportedFormats();
        }
        return [];
    }
}

// Export for use
window.BarcodeScanner = BarcodeScanner;

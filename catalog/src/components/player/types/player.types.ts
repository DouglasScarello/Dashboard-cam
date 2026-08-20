/**
 * Contratos de Tipos e Interfaces para o Ecossistema Tactical Video Player C4ISR
 */

export type StreamingProtocol = 'WEBRTC' | 'HLS' | 'DIRECT_MP4' | 'NONE';

export type StreamingStatus =
    | 'IDLE'
    | 'CONNECTING'
    | 'LIVE_WEBRTC'
    | 'LIVE_HLS'
    | 'PAUSED'
    | 'ERROR'
    | 'RECONNECTING';

export type VisualPreset =
    | 'NORMAL'
    | 'NIGHT_VISION'
    | 'THERMAL_IRONBOW'
    | 'THERMAL_WHITE_HOT'
    | 'PLATE_ALPR_OPTIMIZED'
    | 'SOBEL_EDGES';

export type EnhanceTargetType = 'plate' | 'face' | 'general';

export type InteractiveTool = 'PAN' | 'LOUPE' | 'ROI_SELECT';

export interface ImageFilters {
    brightness: number;  // -1.0 a +1.0 (padrão: 0.0)
    contrast: number;    // 0.0 a 3.0 (padrão: 1.0)
    gamma: number;       // 0.2 a 2.5 (padrão: 1.0)
    sharpenEnabled: boolean;
    sharpenStrength: number; // 0.0 a 1.0 (0 a 100%)
    claheEnabled: boolean;
    claheAmount: number;     // 0.0 a 2.0 (padrão: 1.0)
    claheClipLimit: number;  // 1.0 a 5.0 (padrão: 2.5)
    nightVisionEnabled: boolean;
    nightVisionNoise: number; // 0.0 a 1.0 (padrão: 0.15)
    thermalPalette: 'none' | 'ironbow' | 'rainbow' | 'white_hot';
    edgeEnabled: boolean;
    edgeThreshold: number; // 0.0 a 1.0 (padrão: 0.12)
}

export const DEFAULT_IMAGE_FILTERS: ImageFilters = {
    brightness: 0.0,
    contrast: 1.0,
    gamma: 1.0,
    sharpenEnabled: false,
    sharpenStrength: 0.6,
    claheEnabled: false,
    claheAmount: 1.0,
    claheClipLimit: 2.5,
    nightVisionEnabled: false,
    nightVisionNoise: 0.15,
    thermalPalette: 'none',
    edgeEnabled: false,
    edgeThreshold: 0.12,
};

export interface StreamTelemetry {
    fps: number;
    bitrateMbps: number;
    resolution: string;
    bufferSeconds: number;
    latencyMs: number;
    isLive: boolean;
    qualityLevels: string[];
    currentLevel: number;
    protocol: StreamingProtocol;
}

export interface TransformMatrix {
    scale: number;
    translateX: number;
    translateY: number;
}

export interface LoupeState {
    enabled: boolean;
    x: number;
    y: number;
    zoomFactor: number;
    radius: number;
    isLocked: boolean;
}

export interface ROISelection {
    startX: number;
    startY: number;
    endX: number;
    endY: number;
    isSelecting: boolean;
}

export interface CameraData {
    id: string | number;
    nome: string;
    local?: string | null;
    endereco?: string | null;
    cidade?: string | null;
    uf?: string | null;
    tipo_area?: string | null;
    setor?: string;
    pais?: string;
    thumbnail_url?: string;
    url?: string;
    video_id?: string;
    lat?: number | null;
    long?: number | null;
}

export interface ForensicSnapshotData {
    dataUrl: string;
    sha256: string;
    timestampZulu: string;
    timestampLocal: string;
    cameraId: string | number;
    cameraName: string;
    coordinates: string;
    width: number;
    height: number;
    cropRoi?: { x: number; y: number; width: number; height: number };
}

export interface ForensicSRResult {
    status: string;
    roi_type: string;
    model_used: string;
    original_dimensions: [number, number];
    enhanced_dimensions: [number, number];
    processing_time_ms: number;
    sha256_original: string;
    sha256_enhanced: string;
    quality_metrics_original: Record<string, number>;
    quality_metrics_enhanced: Record<string, number>;
    plate_ocr_candidate?: string | null;
    plate_format?: string | null;
    enhanced_image_base64: string;
    binary_image_base64?: string | null;
    timestamp_utc: string;
}

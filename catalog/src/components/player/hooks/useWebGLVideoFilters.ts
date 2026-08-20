import React, { useEffect, useRef, useState } from 'react';
import { ImageFilters } from '../types/player.types';

// ============================================================================
// SHADERS GLSL (VERTEX & FRAGMENT) — BASEADO NA PESQUISA FORENSE DE CFTV
// ============================================================================

const VERTEX_SHADER_SOURCE = `
  attribute vec2 a_position;
  attribute vec2 a_texCoord;
  varying vec2 v_uv;

  void main() {
    gl_Position = vec4(a_position, 0.0, 1.0);
    // Inversão vertical na GPU para alinhamento 1:1 da textura do frame
    v_uv = vec2(a_texCoord.x, 1.0 - a_texCoord.y);
  }
`;

const FRAGMENT_SHADER_SOURCE = `
  precision mediump float;

  varying vec2 v_uv;
  uniform sampler2D u_image;
  uniform vec2 u_texSize;
  uniform float u_time;

  // Uniformes Fotométricos Básicos
  uniform float u_brightness; // Adição Escalar (-1.0 a 1.0)
  uniform float u_contrast;   // Multiplicador de Expansão (0.0 a 3.0, base 1.0)
  uniform float u_gamma;

  // Uniformes de Máscara de Nitidez (3x3 Unsharp Convolution Kernel)
  uniform int u_sharpenEnabled;
  uniform float u_sharpenStrength; // Intensidade (0.0 a 2.0)

  // Uniformes de CLAHE / Equalização Adaptativa Local
  uniform int u_claheEnabled;
  uniform float u_claheAmount;
  uniform float u_claheClipLimit;

  // Uniformes de Visão Noturna e Termografia
  uniform int u_nightVisionEnabled;
  uniform float u_nightVisionNoise;
  uniform int u_thermalMode; // 0: off, 1: ironbow, 2: rainbow, 3: white_hot

  // Uniformes de Detecção de Borda (Sobel)
  uniform int u_edgeEnabled;
  uniform float u_edgeThreshold;

  // Helper: Extração de Luminância Rec.709
  float getLuminance(vec3 color) {
    return dot(color, vec3(0.2126, 0.7152, 0.0722));
  }

  // Paleta Térmica FLIR Ironbow Procedural
  vec3 getIronbow(float t) {
    t = clamp(t, 0.0, 1.0);
    vec3 c0 = vec3(0.0, 0.0, 0.0);        // Preto
    vec3 c1 = vec3(0.18, 0.0, 0.42);      // Roxo escuro
    vec3 c2 = vec3(0.65, 0.05, 0.55);     // Magenta
    vec3 c3 = vec3(0.92, 0.35, 0.05);     // Laranja avermelhado
    vec3 c4 = vec3(0.98, 0.88, 0.20);     // Amarelo
    vec3 c5 = vec3(1.0, 1.0, 1.0);        // Branco

    if (t < 0.2) return mix(c0, c1, t / 0.2);
    if (t < 0.4) return mix(c1, c2, (t - 0.2) / 0.2);
    if (t < 0.6) return mix(c2, c3, (t - 0.4) / 0.2);
    if (t < 0.8) return mix(c3, c4, (t - 0.6) / 0.2);
    return mix(c4, c5, (t - 0.8) / 0.2);
  }

  // Paleta Térmica Rainbow / Jet
  vec3 getRainbow(float t) {
    t = clamp(t, 0.0, 1.0);
    float r = clamp(min(4.0 * t - 1.5, -4.0 * t + 4.5), 0.0, 1.0);
    float g = clamp(min(4.0 * t - 0.5, -4.0 * t + 3.5), 0.0, 1.0);
    float b = clamp(min(4.0 * t + 0.5, -4.0 * t + 2.5), 0.0, 1.0);
    return vec3(r, g, b);
  }

  // Ruído Pseudo-aleatório para ruído analógico
  float rand(vec2 co) {
    return fract(sin(dot(co, vec2(12.9898, 78.233))) * 43758.5453);
  }

  void main() {
    vec2 step = 1.0 / u_texSize;
    vec4 baseColor = texture2D(u_image, v_uv);
    vec3 color = baseColor.rgb;

    // 1. MÁSCARA DE NITIDEZ PERICIAL (3x3 Convolution Kernel: [-1 -1 -1; -1 +9 -1; -1 -1 -1])
    if (u_sharpenEnabled == 1 && u_sharpenStrength > 0.0) {
      vec3 tl = texture2D(u_image, v_uv + vec2(-step.x,  step.y)).rgb;
      vec3 tc = texture2D(u_image, v_uv + vec2(    0.0,  step.y)).rgb;
      vec3 tr = texture2D(u_image, v_uv + vec2( step.x,  step.y)).rgb;
      vec3 ml = texture2D(u_image, v_uv + vec2(-step.x,     0.0)).rgb;
      vec3 mr = texture2D(u_image, v_uv + vec2( step.x,     0.0)).rgb;
      vec3 bl = texture2D(u_image, v_uv + vec2(-step.x, -step.y)).rgb;
      vec3 bc = texture2D(u_image, v_uv + vec2(    0.0, -step.y)).rgb;
      vec3 br = texture2D(u_image, v_uv + vec2( step.x, -step.y)).rgb;

      // Convolução com 8 vizinhos periféricos
      vec3 neighbors = tl + tc + tr + ml + mr + bl + bc + br;
      vec3 sharpColor = (9.0 * color) - neighbors;
      color = mix(color, clamp(sharpColor, 0.0, 1.0), u_sharpenStrength);
    }

    // 2. CLAHE / EQUALIZAÇÃO ADAPTATIVA LOCAL (9-tap sampling)
    if (u_claheEnabled == 1) {
      float currentLum = getLuminance(color);
      vec2 offset = step * 2.5;

      float l_n  = getLuminance(texture2D(u_image, v_uv + vec2(0.0, offset.y)).rgb);
      float l_s  = getLuminance(texture2D(u_image, v_uv - vec2(0.0, offset.y)).rgb);
      float l_w  = getLuminance(texture2D(u_image, v_uv - vec2(offset.x, 0.0)).rgb);
      float l_e  = getLuminance(texture2D(u_image, v_uv + vec2(offset.x, 0.0)).rgb);
      float l_nw = getLuminance(texture2D(u_image, v_uv + vec2(-offset.x,  offset.y)).rgb);
      float l_ne = getLuminance(texture2D(u_image, v_uv + vec2( offset.x,  offset.y)).rgb);
      float l_sw = getLuminance(texture2D(u_image, v_uv + vec2(-offset.x, -offset.y)).rgb);
      float l_se = getLuminance(texture2D(u_image, v_uv + vec2( offset.x, -offset.y)).rgb);

      float localMean = (currentLum + l_n + l_s + l_w + l_e + l_nw + l_ne + l_sw + l_se) / 9.0;
      float dev = abs(currentLum - localMean) + abs(l_n - localMean) + abs(l_s - localMean) + 
                  abs(l_w - localMean) + abs(l_e - localMean);
      float localStd = dev / 5.0;

      float gain = min(0.5 / (localStd + 0.02), u_claheClipLimit) * u_claheAmount;
      float newLum = clamp(localMean + (currentLum - localMean) * gain, 0.0, 1.0);

      if (currentLum > 0.001) {
        color = clamp(color * (newLum / currentLum), 0.0, 1.0);
      } else {
        color = vec3(newLum);
      }
    }

    // 3. FOTOMETRIA RIGOROSA: BRILHO (Adição Linear) & CONTRASTE (Deslocamento em 0.5)
    color.rgb += u_brightness;
    color.rgb = (color.rgb - 0.5) * u_contrast + 0.5;
    color.rgb = clamp(color.rgb, 0.0, 1.0);

    if (u_gamma > 0.0 && u_gamma != 1.0) {
      color = pow(color, vec3(1.0 / u_gamma));
    }

    // 4. DETECTOR DE BORDAS SOBEL (Realce de Caracteres / Placas)
    if (u_edgeEnabled == 1) {
      float tl = getLuminance(texture2D(u_image, v_uv + vec2(-step.x,  step.y)).rgb);
      float tc = getLuminance(texture2D(u_image, v_uv + vec2(    0.0,  step.y)).rgb);
      float tr = getLuminance(texture2D(u_image, v_uv + vec2( step.x,  step.y)).rgb);
      float ml = getLuminance(texture2D(u_image, v_uv + vec2(-step.x,     0.0)).rgb);
      float mr = getLuminance(texture2D(u_image, v_uv + vec2( step.x,     0.0)).rgb);
      float bl = getLuminance(texture2D(u_image, v_uv + vec2(-step.x, -step.y)).rgb);
      float bc = getLuminance(texture2D(u_image, v_uv + vec2(    0.0, -step.y)).rgb);
      float br = getLuminance(texture2D(u_image, v_uv + vec2( step.x, -step.y)).rgb);

      float gx = -tl - 2.0 * ml - bl + tr + 2.0 * mr + br;
      float gy = -tl - 2.0 * tc - tr + bl + 2.0 * bc + br;
      float edgeVal = sqrt(gx * gx + gy * gy);

      float edgeIntensity = smoothstep(u_edgeThreshold, u_edgeThreshold + 0.15, edgeVal);
      color = vec3(edgeIntensity * 0.1, edgeIntensity * 0.95, edgeIntensity * 1.0);
    }

    // 5. VISÃO NOTURNA (Fósforo Verde P43 + Ruído + Scanlines)
    if (u_nightVisionEnabled == 1) {
      float lum = getLuminance(color);
      lum = pow(lum, 0.65) * 1.4;

      vec3 phosphorGreen = vec3(lum * 0.15, lum * 1.05, lum * 0.25);
      float noise = (rand(v_uv + fract(u_time * 1.5)) - 0.5) * u_nightVisionNoise;
      float scanline = sin(v_uv.y * u_texSize.y * 1.5) * 0.04;
      float dist = distance(v_uv, vec2(0.5));
      float vignette = smoothstep(0.75, 0.35, dist);

      color = clamp((phosphorGreen + vec3(noise) - vec3(scanline)) * vignette, 0.0, 1.0);
    }

    // 6. VISÃO TÉRMICA FLIR
    if (u_thermalMode == 1) {
      float t = getLuminance(color);
      color = getIronbow(t);
    } else if (u_thermalMode == 2) {
      float t = getLuminance(color);
      color = getRainbow(t);
    } else if (u_thermalMode == 3) {
      float t = 1.0 - getLuminance(color);
      color = vec3(t);
    }

    gl_FragColor = vec4(color, baseColor.a);
  }
`;

function compileShader(gl: WebGLRenderingContext, type: number, source: string): WebGLShader | null {
    const shader = gl.createShader(type);
    if (!shader) return null;
    gl.shaderSource(shader, source);
    gl.compileShader(shader);

    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        console.error('WebGL Shader Compile Error:', gl.getShaderInfoLog(shader));
        gl.deleteShader(shader);
        return null;
    }
    return shader;
}

function createProgram(
    gl: WebGLRenderingContext,
    vertexSrc: string,
    fragmentSrc: string
): { program: WebGLProgram; vs: WebGLShader; fs: WebGLShader } | null {
    const vs = compileShader(gl, gl.VERTEX_SHADER, vertexSrc);
    const fs = compileShader(gl, gl.FRAGMENT_SHADER, fragmentSrc);
    if (!vs || !fs) return null;

    const program = gl.createProgram();
    if (!program) return null;

    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);

    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        console.error('WebGL Program Link Error:', gl.getProgramInfoLog(program));
        gl.deleteProgram(program);
        return null;
    }
    return { program, vs, fs };
}

export interface UseWebGLVideoFiltersProps {
    videoRef: React.RefObject<HTMLVideoElement | null>;
    canvasRef: React.RefObject<HTMLCanvasElement | null>;
    filters: ImageFilters;
}

export function useWebGLVideoFilters({ videoRef, canvasRef, filters }: UseWebGLVideoFiltersProps) {
    const filtersRef = useRef<ImageFilters>(filters);
    filtersRef.current = filters;

    const [fps, setFps] = useState<number>(0);
    const [isReady, setIsReady] = useState<boolean>(false);

    useEffect(() => {
        const video = videoRef.current;
        const canvas = canvasRef.current;
        if (!video || !canvas) return;

        const gl = canvas.getContext('webgl', {
            alpha: false,
            antialias: false,
            depth: false,
            stencil: false,
            preserveDrawingBuffer: true,
            powerPreference: 'high-performance',
        }) as WebGLRenderingContext | null;

        if (!gl) {
            console.error('WebGL não disponível.');
            return;
        }

        const compiled = createProgram(gl, VERTEX_SHADER_SOURCE, FRAGMENT_SHADER_SOURCE);
        if (!compiled) return;
        const { program, vs, fs } = compiled;
        gl.useProgram(program);

        // Quad 2D
        const positionBuffer = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
        gl.bufferData(
            gl.ARRAY_BUFFER,
            new Float32Array([
                -1.0, -1.0,
                 1.0, -1.0,
                -1.0,  1.0,
                -1.0,  1.0,
                 1.0, -1.0,
                 1.0,  1.0,
            ]),
            gl.STATIC_DRAW
        );

        const texCoordBuffer = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, texCoordBuffer);
        gl.bufferData(
            gl.ARRAY_BUFFER,
            new Float32Array([
                0.0, 0.0,
                1.0, 0.0,
                0.0, 1.0,
                0.0, 1.0,
                1.0, 0.0,
                1.0, 1.0,
            ]),
            gl.STATIC_DRAW
        );

        const aPositionLocation = gl.getAttribLocation(program, 'a_position');
        gl.enableVertexAttribArray(aPositionLocation);
        gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
        gl.vertexAttribPointer(aPositionLocation, 2, gl.FLOAT, false, 0, 0);

        const aTexCoordLocation = gl.getAttribLocation(program, 'a_texCoord');
        gl.enableVertexAttribArray(aTexCoordLocation);
        gl.bindBuffer(gl.ARRAY_BUFFER, texCoordBuffer);
        gl.vertexAttribPointer(aTexCoordLocation, 2, gl.FLOAT, false, 0, 0);

        // Uniforms
        const uImageLoc = gl.getUniformLocation(program, 'u_image');
        const uTexSizeLoc = gl.getUniformLocation(program, 'u_texSize');
        const uTimeLoc = gl.getUniformLocation(program, 'u_time');
        const uBrightnessLoc = gl.getUniformLocation(program, 'u_brightness');
        const uContrastLoc = gl.getUniformLocation(program, 'u_contrast');
        const uGammaLoc = gl.getUniformLocation(program, 'u_gamma');
        const uSharpenEnabledLoc = gl.getUniformLocation(program, 'u_sharpenEnabled');
        const uSharpenStrengthLoc = gl.getUniformLocation(program, 'u_sharpenStrength');
        const uClaheEnabledLoc = gl.getUniformLocation(program, 'u_claheEnabled');
        const uClaheAmountLoc = gl.getUniformLocation(program, 'u_claheAmount');
        const uClaheClipLimitLoc = gl.getUniformLocation(program, 'u_claheClipLimit');
        const uNightVisionEnabledLoc = gl.getUniformLocation(program, 'u_nightVisionEnabled');
        const uNightVisionNoiseLoc = gl.getUniformLocation(program, 'u_nightVisionNoise');
        const uThermalModeLoc = gl.getUniformLocation(program, 'u_thermalMode');
        const uEdgeEnabledLoc = gl.getUniformLocation(program, 'u_edgeEnabled');
        const uEdgeThresholdLoc = gl.getUniformLocation(program, 'u_edgeThreshold');

        // Textura
        const texture = gl.createTexture();
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, texture);

        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);

        let textureAllocated = false;
        let allocatedWidth = 0;
        let allocatedHeight = 0;
        let frameCount = 0;
        let lastFpsTime = performance.now();
        let rVfcId: number | null = null;
        let rAfId: number | null = null;
        let isDestroyed = false;

        const renderFrame = (now: number) => {
            if (isDestroyed) return;

            if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && video.videoWidth > 0) {
                const vWidth = video.videoWidth;
                const vHeight = video.videoHeight;

                if (canvas.width !== vWidth || canvas.height !== vHeight) {
                    canvas.width = vWidth;
                    canvas.height = vHeight;
                    gl.viewport(0, 0, vWidth, vHeight);
                }

                gl.bindTexture(gl.TEXTURE_2D, texture);

                if (!textureAllocated || allocatedWidth !== vWidth || allocatedHeight !== vHeight) {
                    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, video);
                    textureAllocated = true;
                    allocatedWidth = vWidth;
                    allocatedHeight = vHeight;
                    setIsReady(true);
                } else {
                    gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, gl.RGBA, gl.UNSIGNED_BYTE, video);
                }

                const f = filtersRef.current;
                gl.uniform1i(uImageLoc, 0);
                gl.uniform2f(uTexSizeLoc, vWidth, vHeight);
                gl.uniform1f(uTimeLoc, now * 0.001);

                gl.uniform1f(uBrightnessLoc, f.brightness);
                gl.uniform1f(uContrastLoc, f.contrast);
                gl.uniform1f(uGammaLoc, f.gamma);

                gl.uniform1i(uSharpenEnabledLoc, f.sharpenEnabled ? 1 : 0);
                gl.uniform1f(uSharpenStrengthLoc, f.sharpenStrength);

                gl.uniform1i(uClaheEnabledLoc, f.claheEnabled ? 1 : 0);
                gl.uniform1f(uClaheAmountLoc, f.claheAmount);
                gl.uniform1f(uClaheClipLimitLoc, f.claheClipLimit);

                gl.uniform1i(uNightVisionEnabledLoc, f.nightVisionEnabled ? 1 : 0);
                gl.uniform1f(uNightVisionNoiseLoc, f.nightVisionNoise);

                let thermalMode = 0;
                if (f.thermalPalette === 'ironbow') thermalMode = 1;
                else if (f.thermalPalette === 'rainbow') thermalMode = 2;
                else if (f.thermalPalette === 'white_hot') thermalMode = 3;
                gl.uniform1i(uThermalModeLoc, thermalMode);

                gl.uniform1i(uEdgeEnabledLoc, f.edgeEnabled ? 1 : 0);
                gl.uniform1f(uEdgeThresholdLoc, f.edgeThreshold);

                gl.drawArrays(gl.TRIANGLES, 0, 6);

                frameCount++;
                if (now - lastFpsTime >= 1000) {
                    setFps(Math.round((frameCount * 1000) / (now - lastFpsTime)));
                    frameCount = 0;
                    lastFpsTime = now;
                }
            }

            if ('requestVideoFrameCallback' in video) {
                rVfcId = (video as any).requestVideoFrameCallback(renderFrame);
            } else {
                rAfId = requestAnimationFrame(renderFrame);
            }
        };

        if ('requestVideoFrameCallback' in video) {
            rVfcId = (video as any).requestVideoFrameCallback(renderFrame);
        } else {
            rAfId = requestAnimationFrame(renderFrame);
        }

        const handleContextLost = (e: Event) => {
            e.preventDefault();
            console.warn('WebGL Context Lost. Aguardando recuperação...');
            if (rVfcId && 'cancelVideoFrameCallback' in video) {
                (video as any).cancelVideoFrameCallback(rVfcId);
            }
            if (rAfId) cancelAnimationFrame(rAfId);
        };

        const handleContextRestored = () => {
            console.info('WebGL Context Restored.');
            textureAllocated = false;
        };

        canvas.addEventListener('webglcontextlost', handleContextLost, false);
        canvas.addEventListener('webglcontextrestored', handleContextRestored, false);

        return () => {
            isDestroyed = true;
            if (rVfcId && 'cancelVideoFrameCallback' in video) {
                (video as any).cancelVideoFrameCallback(rVfcId);
            }
            if (rAfId) cancelAnimationFrame(rAfId);

            canvas.removeEventListener('webglcontextlost', handleContextLost);
            canvas.removeEventListener('webglcontextrestored', handleContextRestored);

            if (texture) gl.deleteTexture(texture);
            if (positionBuffer) gl.deleteBuffer(positionBuffer);
            if (texCoordBuffer) gl.deleteBuffer(texCoordBuffer);
            if (vs) gl.deleteShader(vs);
            if (fs) gl.deleteShader(fs);
            if (program) gl.deleteProgram(program);

            const loseContext = gl.getExtension('WEBGL_lose_context');
            if (loseContext) loseContext.loseContext();
        };
    }, [videoRef, canvasRef]);

    return { fps, isReady };
}

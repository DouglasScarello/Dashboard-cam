# Módulo 06: Segurança Ofensiva/Defensiva, Ghost Protocol e Air-Gap Tático

## 1. Arquitetura True Air-Gap & Mitigação de Vazamento de Rede

### 1.1. Vetores de Exfiltração & Contramedidas
- **WebRTC IP Leak**: Chamadas de coleta de candidatos ICE via STUN/TURN contornam interfaces de VPN ao consultar servidores públicos.
  - *Mitigação*: Desativação completa de STUN/TURN; bloqueio de portas 3478 e 5349 UDP/TCP via `nftables`; isolamento dos processos de ingestão em **Network Namespaces** (`ip netns`) dedicados sem gateway para a WAN.
- **DNS Leaks**: Chamadas libc `getaddrinfo` que consultam servidores não autorizados.
  - *Mitigação*: Desativação total de DNS ou resolvedor local Unbound em loopback com root zone estática e DNSSEC; descarte das portas 53 e 853.
- **DPI e STUN Bypass**:
  - *Mitigação*: Filtros eBPF/XDP descartando o Magic Cookie STUN (`0x2112A442`).

### 1.2. Regras nftables em Modo Stealth
```nftables
table inet stealth_filter {
    chain input {
        type filter hook input priority filter; policy drop;
        iif "lo" accept
        ct state established,related accept
    }
    chain output {
        type filter hook output priority filter; policy drop;
        oif "lo" accept
        ct state established,related accept
        # Apenas comunicação com a subnet da rede de câmeras locais
        ip daddr 192.168.10.0/24 accept
    }
}
```

---

## 2. Sandboxing e Isolamento de Decodificadores de Vídeo

Decodificadores de vídeo (FFmpeg, libavcodec, libjpeg) processam fluxos de câmeras e possuem histórico crítico de vulnerabilidades de corrupção de memória.

### 2.1. Camadas de Confinamento
1. **Seccomp-BPF**: Restrição de syscalls permitindo apenas `read`, `write`, `futex`, `epoll_wait` e `ioctl` em `/dev/video*`. Syscalls perigosas (`execve`, `ptrace`, `clone(CLONE_NEW*)`) abortam com `SCMP_ACT_KILL_PROCESS`.
2. **AppArmor MAC**: Perfil exclusivo negando acesso a `/home`, `/etc/shadow`, `/proc/kcore` e capabilities como `CAP_SYS_ADMIN` e `CAP_NET_RAW`.
3. **cgroups v2**: Quotas estritas (`memory.max = 2GB`, `pids.max = 32`, `cpu.max`) com OOM killer dedicado.
4. **Rootless & Nsjail / Bubblewrap**: Execução sob UID desprivilegiado (nobody / 65534) em sistema de arquivos raiz montado em modo Read-Only.

---

## 3. Killswitches Físicos/Software & Anti-Forensics

### 3.1. Mitigação de Cold Boot Attacks (RAM Crypto-Wipe)
- Chaves simétricas alocadas em memória bloqueada (`mlock`) e marcadas com `MADV_DONTDUMP` para evitar gravação em swap ou core dumps.
- Uso de registradores SSE/AVX dedicados para retenção de chaves temporárias (arquitetura estilo *TRESOR*).
- Limpeza forçada com barreira explícita de compilador:
```c
static inline void secure_memzero(void *v, size_t n) {
    volatile unsigned char *p = (volatile unsigned char *)v;
    while (n--) *p++ = 0;
    __asm__ __volatile__ ("" : : "r"(v) : "memory");
}
```

### 3.2. Sequência de Pânico e Crypto-Shredding (< 5 ms)
1. **Trigger**: Pino GPIO conectado a botão de pânico físico ou sensor de violação de chassi (Tamper Switch).
2. **Crypto-Shredding**: Sobrescrita atômica do cabeçalho LUKS2 no SSD com bytes aleatórios / 0xFF (`cryptsetup erase`), inviabilizando qualquer recuperação de dados.
3. **Emergency Panic**: Disparo de SysRq trigger `c` (`echo c > /proc/sysrq-trigger`), travando o kernel instantaneamente sem sincronizar buffers no disco.

---

## 4. Criptografia em Repouso e em Trânsito

### 4.1. Repouso (Data at Rest)
- **Full Disk Encryption (FDE)**: LUKS2 com `AES-256-XTS`, chave de 512 bits e KDF `Argon2id` (1GB RAM, 6 iterações).
- **Evidências e Dossiês**: Envelope Encryption com **AES-256-GCM / EAX** e autenticação AEAD.

### 4.2. Trânsito (Data in Transit)
- **WireGuard Tático P2P**: Noise Protocol Framework (Curve25519, ChaCha20, Poly1305, BLAKE2s) com descarte silencioso de pacotes não assinados e Perfect Forward Secrecy (PFS).
- **mTLS 1.3**: Certificados ED25519 e pinagem de chaves compilada no binário dos nós.

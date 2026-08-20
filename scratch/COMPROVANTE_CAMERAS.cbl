      ******************************************************************
      * SISTEMA DE INTELIGENCIA C4ISR - OLHO DE DEUS
      * MODULO BANCARIO / FORENSE DE EMISSAO DE COMPROVANTE DE LOCAL
      * LINGUAGEM: COBOL (ANSI 85 STANDARD)
      * AUTOR: DIVISAO DE ENGENHARIA DE DADOS & CUSTODIA FORENSE
      ******************************************************************
       IDENTIFICATION DIVISION.
       PROGRAM-ID. EMISREC.
       AUTHOR. OLHO-DE-DEUS-C4ISR.
       INSTALLATION. DATACENTER-SEGURANCA-NACIONAL.
       DATE-WRITTEN. 20/08/2026.
       DATE-COMPILED. 20/08/2026.
       SECURITY. CONFIDENCIAL - USO INTERNO.

       ENVIRONMENT DIVISION.
       CONFIGURATION SECTION.
       SOURCE-COMPUTER. LINUX-X86-64.
       OBJECT-COMPUTER. LINUX-X86-64.
       SPECIAL-NAMES.
           DECIMAL-POINT IS COMMA.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
      *-----------------------------------------------------------------
      * CAMPOS DE CONTROLE E REGISTRO DE MONITORAMENTO
      *-----------------------------------------------------------------
       01 WS-CABECALHO.
          05 FILLER             PIC X(70) VALUE ALL "=".
          05 WS-TIT-BANCO       PIC X(70) VALUE 
             "       SISTEMA INTEGRADO DE VIGILANCIA C4ISR - OLHO DE DEUS       ".
          05 WS-TIT-DOC         PIC X(70) VALUE 
             "            CERTIFICADO / COMPROVANTE DE GEOLOCALIZACAO            ".
          05 FILLER             PIC X(70) VALUE ALL "-".

       01 WS-DADOS-CAMERA.
          05 WS-CAM-ID          PIC X(12) VALUE "CAM_BR_0001 ".
          05 WS-CAM-NOME        PIC X(45) VALUE 
             "BALNEARIO CAMBORIU - AV. ATLANTICA           ".
          05 WS-CAM-ENDERECO    PIC X(50) VALUE 
             "AV. ATLANTICA (ORLA CENTRAL - BARRA SUL)          ".
          05 WS-CAM-CIDADE      PIC X(30) VALUE 
             "BALNEARIO CAMBORIU            ".
          05 WS-CAM-UF          PIC X(02) VALUE "SC".
          05 WS-CAM-PAIS        PIC X(06) VALUE "BRASIL".
          05 WS-CAM-TIPO        PIC X(25) VALUE 
             "ORLA / PRAIA PUBLICA     ".
          05 WS-CAM-STATUS      PIC X(10) VALUE "ONLINE    ".
          05 WS-CAM-LAT         PIC -(03)9,9999 VALUE -026,9926.
          05 WS-CAM-LONG        PIC -(03)9,9999 VALUE -048,6347.

       01 WS-DADOS-EMISSAO.
          05 WS-DATA-ATUAL.
             10 WS-ANO          PIC 9(04) VALUE 2026.
             10 WS-MES          PIC 9(02) VALUE 08.
             10 WS-DIA          PIC 9(02) VALUE 20.
          05 WS-HORA-ATUAL.
             10 WS-HORA         PIC 9(02) VALUE 21.
             10 WS-MIN          PIC 9(02) VALUE 45.
             10 WS-SEG          PIC 9(02) VALUE 30.
          05 WS-TERMINAL        PIC X(16) VALUE "SRV-C4ISR-NODE01".
          05 WS-HASH-AUTENTICACAO PIC X(36) VALUE 
             "9E8A-7B4C-22F1-8830-5DAE-6109-FF3C21".

       01 WS-RODAPE.
          05 FILLER             PIC X(70) VALUE ALL "-".
          05 WS-MSG-AUTENTIC    PIC X(70) VALUE 
             "AUTENTICACAO BANCARIA / PROTOCOLO FORENSE ICP-BRASIL: VALIDO".
          05 FILLER             PIC X(70) VALUE ALL "=".

      *-----------------------------------------------------------------
       PROCEDURE DIVISION.
       0000-PRINCIPAL.
           PERFORM 1000-EXIBIR-CABECALHO
           PERFORM 2000-EXIBIR-DADOS-CAMERA
           PERFORM 3000-EXIBIR-AUTENTICACAO
           PERFORM 4000-EXIBIR-RODAPE
           STOP RUN.

       1000-EXIBIR-CABECALHO.
           DISPLAY WS-CABECALHO (1:70)
           DISPLAY WS-TIT-BANCO
           DISPLAY WS-TIT-DOC
           DISPLAY WS-CABECALHO (71:70)
           DISPLAY "DATA DE EMISSAO: " WS-DIA "/" WS-MES "/" WS-ANO 
                   "   HORA: " WS-HORA ":" WS-MIN ":" WS-SEG
           DISPLAY "TERMINAL AUTORIZADO: " WS-TERMINAL
           DISPLAY WS-CABECALHO (71:70).

       2000-EXIBIR-DADOS-CAMERA.
           DISPLAY "IDENTIFICADOR DO DISPOSITIVO : " WS-CAM-ID
           DISPLAY "NOME DO PONTO DE VIGILANCIA  : " WS-CAM-NOME
           DISPLAY "LOGRADOURO / ENDERECO EXATO  : " WS-CAM-ENDERECO
           DISPLAY "MUNICIPIO / UNIDADE FEDERATIVA: " WS-CAM-CIDADE " / " WS-CAM-UF
           DISPLAY "PAIS DE ORIGEM DA TRANSMISSAO: " WS-CAM-PAIS
           DISPLAY "CATEGORIA / TIPO DE AREA     : " WS-CAM-TIPO
           DISPLAY "STATUS OPERACIONAL DO SENSOR : " WS-CAM-STATUS
           DISPLAY "COORDENADA LATITUDE (GPS)    : " WS-CAM-LAT
           DISPLAY "COORDENADA LONGITUDE (GPS)   : " WS-CAM-LONG.

       3000-EXIBIR-AUTENTICACAO.
           DISPLAY WS-RODAPE (1:70)
           DISPLAY "CHAVE HASH DE CUSTODIA BANCARIA:"
           DISPLAY WS-HASH-AUTENTICACAO
           DISPLAY "FINALIDADE: LAUDO DE LOCALIZACAO E PROVA PERICIAL".

       4000-EXIBIR-RODAPE.
           DISPLAY WS-MSG-AUTENTIC
           DISPLAY WS-RODAPE (71:70).

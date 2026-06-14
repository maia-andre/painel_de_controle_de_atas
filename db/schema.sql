-- ============================================================================
-- Painel de Controle de Atas — Schema PostgreSQL (Fase 1 da migração)
-- ============================================================================
-- Modela o que hoje vive em CSV/XLSX na raiz. As regras de negócio NÃO mudam:
-- o capping de 100%, a métrica de SV (valor x quantidade) e o "preço praticado"
-- continuam na aplicação / nas views, não aqui.
--
-- Convenções travadas no planejamento:
--   * Chave de ata = (numero_ata, ano) com zeros à esquerda removidos na carga.
--   * Previsto NUNCA usa valor unitário da SD (dado errado) — coluna não existe.
--   * Consumo é guardado BRUTO; o filtro de cancelado (prefixo 'CANCELAD' em
--     status_rc OU status_af) é aplicado na view/consulta, preservando auditoria.
--   * Origem do previsto é polimórfica: tipo_doc ∈ {SD, ETP}.
-- ============================================================================

-- --------------------------------------------------------------------------
-- Dimensão: Secretarias (substitui o dicionário hardcoded do app.py)
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS secretarias (
    codigo  INTEGER PRIMARY KEY,
    sigla   TEXT NOT NULL,
    nome    TEXT
);

INSERT INTO secretarias (codigo, sigla) VALUES
    (5,  'GP'),     (10, 'SG'),    (15, 'SAJ'),   (20, 'SGAF'),
    (30, 'SEURBS'), (35, 'SGO'),   (40, 'SEC'),   (45, 'SEQV'),
    (50, 'SASC'),   (55, 'SMC'),   (60, 'SS'),    (65, 'SEMOB'),
    (70, 'SEPAC'),  (75, 'SIDE'),  (80, 'EG'),    (90, 'SHRF')
ON CONFLICT (codigo) DO NOTHING;

-- --------------------------------------------------------------------------
-- Metadados das atas (origem: base_sds.xlsx) — editável por tela na Fase 1.5
-- vigencia_inicio = data de assinatura.
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS atas (
    id              SERIAL PRIMARY KEY,
    numero_ata      TEXT NOT NULL,
    ano             TEXT,
    objeto          TEXT,
    vigencia_inicio DATE,            -- = assinatura
    vigencia_fim    DATE,
    prorrogada      BOOLEAN DEFAULT FALSE,
    UNIQUE (numero_ata, ano)
);

-- --------------------------------------------------------------------------
-- Vínculo manual ata <-> documento E fila dos bots.
-- Substitui: o vínculo de SDs da base_sds.xlsx, a base_etps.csv e os
-- arquivos de checkpoint (log_*_processados.txt).
-- O gestor amarra aqui (tela de administração); o bot lê a fila por status.
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ata_documentos (
    id            SERIAL PRIMARY KEY,
    ata_id        INTEGER REFERENCES atas(id) ON DELETE CASCADE,
    tipo_doc      TEXT NOT NULL CHECK (tipo_doc IN ('SD', 'ETP')),
    numero_doc    TEXT NOT NULL,
    ano_doc       TEXT,
    secretaria    TEXT,                          -- usado pelo bot de ETP
    status        TEXT NOT NULL DEFAULT 'pendente'
                  CHECK (status IN ('pendente', 'processado', 'erro')),
    processado_em TIMESTAMP,
    UNIQUE (tipo_doc, numero_doc, ano_doc)
);

-- --------------------------------------------------------------------------
-- Itens planejados / teto previsto (saída dos bots; origem: previstos_dashboard.csv)
-- ata_id é NULLABLE: previsto de ETP pode não ter ata resolvida ainda.
-- numero_ata/ano ficam denormalizados porque nem toda linha resolve para uma ata.
-- SEM valor_unitario_previsto (dado errado, nunca usar).
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS previstos (
    id                   SERIAL PRIMARY KEY,
    ata_id               INTEGER REFERENCES atas(id),
    numero_ata           TEXT,
    ano                  TEXT,
    codigo_material      TEXT NOT NULL,
    descricao            TEXT,
    unidade              TEXT,                    -- 'SV' => serviço (métrica = valor)
    orgao                TEXT,                    -- Secr. RC bruto
    secretaria_codigo    INTEGER REFERENCES secretarias(codigo),
    qtd_prevista         NUMERIC DEFAULT 0,
    valor_total_previsto NUMERIC DEFAULT 0,
    tipo_doc             TEXT CHECK (tipo_doc IN ('SD', 'ETP')),
    numero_doc           TEXT,
    atualizado_em        TIMESTAMP DEFAULT NOW()
);

-- --------------------------------------------------------------------------
-- Execução financeira: cada linha é uma RC com sua AF (origem: base_rcaf.csv).
-- O consumo é medido pela RC (quantidade/valor); o status da AF e da RC ficam
-- guardados para o filtro de cancelado ser feito na consulta.
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS consumo_rcaf (
    id                SERIAL PRIMARY KEY,
    ata_id            INTEGER REFERENCES atas(id),
    numero_ata        TEXT,
    ano               TEXT,
    codigo_material   TEXT NOT NULL,
    descricao         TEXT,
    orgao             TEXT,                       -- Secr. RC bruto (requisitante)
    secretaria_codigo INTEGER REFERENCES secretarias(codigo),
    numero_rc         TEXT,
    data_rc           DATE,
    status_rc         TEXT,
    numero_af         TEXT,
    status_af         TEXT,
    quantidade        NUMERIC DEFAULT 0,          -- Qtd RC
    valor_unitario    NUMERIC DEFAULT 0,          -- Val.Unit RC (preço praticado)
    valor_total       NUMERIC DEFAULT 0           -- Val.Total RC
);

-- --------------------------------------------------------------------------
-- Índices para os filtros do painel
-- --------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_previstos_mat   ON previstos (codigo_material);
CREATE INDEX IF NOT EXISTS idx_previstos_ata   ON previstos (numero_ata, ano);
CREATE INDEX IF NOT EXISTS idx_consumo_mat     ON consumo_rcaf (codigo_material);
CREATE INDEX IF NOT EXISTS idx_consumo_orgao   ON consumo_rcaf (orgao);
CREATE INDEX IF NOT EXISTS idx_consumo_ata     ON consumo_rcaf (numero_ata, ano);

-- --------------------------------------------------------------------------
-- View de consumo válido: aplica o filtro de cancelado uma única vez.
-- O app deve consumir esta view no lugar da tabela bruta.
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW consumo_valido AS
SELECT *
FROM consumo_rcaf
WHERE COALESCE(UPPER(status_rc), '') NOT LIKE 'CANCELAD%'
  AND COALESCE(UPPER(status_af), '') NOT LIKE 'CANCELAD%';

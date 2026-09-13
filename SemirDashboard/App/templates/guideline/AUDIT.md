# Curriculum Audit — Critical Evaluation

**Date**: 2026-07-03
**Auditor**: AI Senior Instructor (self-review)
**Scope**: 40 modules đã gen (Level 1-7)
**Verdict**: Foundation solid. Cần bổ sung 3 lớp còn thiếu.

---

## 1. Strengths (điểm mạnh)

### 1.1 Simple → Complex progression
- ✅ L1 bắt đầu từ định nghĩa ML (Tom Mitchell), không giả định background
- ✅ L2 build on L1 assumption — bias-variance được explain sau khi đã có tree models
- ✅ L3 nối L2 với dòng "khi nào NN vs XGBoost" — giúp bạn nhớ context
- ✅ L4 dẫn dắt từ tokenization (input side) → attention (engine) → pretraining (learning) → alignment (fine-tune) → inference (serving) — đúng SDLC of building LLM
- ✅ L6 xây trên L4-L5 (agents dùng LLM đã learn ở L4)

### 1.2 Real-world evidence
- ✅ Mỗi module có `Evidence box` chỉ tới file thật trong 2 projects
- ✅ V19.5 death case (L2.6) là gold — cho concrete production failure với 7 root causes
- ✅ V20 Slice 3 SHAP prune (L2.5) — practical interpretability

### 1.3 QA gates
- ✅ Mỗi module có 5 Q&A tự-test
- ✅ Total ~200 questions across 40 modules

### 1.4 References
- ✅ Papers + blogs + videos quốc tế
- ✅ Prioritize seminal papers (Vaswani, He, Devlin, Hu)

---

## 2. Weaknesses (điểm yếu, cần fix)

### 2.1 Content gaps — CRITICAL

#### 2.1.1 AI artifacts (Agents, Skills, MCP) chưa đủ deep
**Vấn đề**: L6 nói về agents nhưng ở LangGraph angle. Không cover:
- Claude Skills (mới quan trọng, ai_orchestrator có `.claude/skills/`)
- Sub-agent hierarchy (parent-child agents, delegation)
- MCP servers + clients + resources + prompts (chỉ mention brief ở L5.3)
- Spec-Driven Development (SDD, SpecKit — ai_orchestrator SpecAnalyze agent dùng)
- Constitutional AI in production (Claude specific)

**Impact cho phỏng vấn**: Software engineer roles đang shift toward "AI-augmented dev" — bạn phải nói được về Cursor, Claude Code, Aider, MCP integration workflows. Curriculum hiện chưa cover đủ.

**Fix**: Thêm Level 8 (6 modules mới) chuyên về AI artifacts + frameworks landscape.

#### 2.1.2 Alignment / Safety philosophy chưa đủ
**Vấn đề**: L5.6 chỉ nói về prompt injection level. Không cover:
- Paperclip maximizer (Bostrom, canonical AI safety thought experiment)
- Instrumental convergence
- Corrigibility / shutdown problem
- Deceptive alignment
- Mesa-optimization
- Constitutional AI in depth (chỉ mention lướt ở L4.4)

**Impact**: Câu hỏi "What's your view on AI safety" hỏi thường xuyên ở senior interviews. Bạn cần vocabulary + arguments.

**Fix**: L8.5 Alignment + paperclip đầy đủ.

#### 2.1.3 Frameworks landscape chưa map
**Vấn đề**: Curriculum tập trung LangGraph. Nhưng interviewer có thể dùng LlamaIndex, DSPy, Semantic Kernel, CrewAI. Bạn cần biết trade-offs.

**Fix**: L8.6 frameworks survey.

### 2.2 Content errors / lỗi nhỏ

#### L2.1 — Regression MSE formula sai indent
Line: `L = Σ (y_i - y_hat_i)²  # MSE`
Should be: `L = (1/N) Σ ...` — MSE là **mean** squared. Current text OK khi define nhưng nên clarify.

#### L3.2 — AdamW formula
Second block writes `- lr · λ · w` — đúng nhưng subtle: PyTorch impl có warm-up decay khác. Nên add note "not exactly this in prod frameworks".

#### L4.2 — Encoder-Decoder Transformer
Nói "T5 uses encoder-decoder" nhưng không mention BART, mBART, mT5, ByT5. Nên list broader family.

#### L4.5 — QLoRA memory calculation
Nói "LLaMA-65B fit 48GB". Đúng với r=64. Nhưng batch=1. Real training batch > 1 cần thêm memory cho activations. Nên clarify với batch/gradient accumulation.

#### L5.2 — RAG Anthropic Contextual Retrieval
Nói "35% accuracy boost" — Anthropic actually reported 49% (for BM25 + embedding + contextual + rerank combined). 35% chỉ với contextual alone. Fix number.

#### L6.4 — Postgres schema
`PRIMARY KEY (thread_id, checkpoint_id)` — thiếu created_at nếu muốn sort ordered checkpoints. LangGraph actual schema có checkpoint_ns, checkpoint_id, parent_checkpoint_id. Simplified nhưng OK cho học.

#### L4.3 — Chinchilla ratio
Nói "D/N ≈ 20 optimal". Original paper: "roughly proportional" — practical is 20. Chinchilla paper actual figure: ~20. Correct.

#### L4.4 — RLHF loss formula
`L_PPO = -E[reward - β · KL(policy || ref)]` — simplified. Real PPO has clipping term `min(ratio × advantage, clip(ratio, 1-ε, 1+ε) × advantage)`. Simplified for teaching OK.

### 2.3 Depth inconsistency

Một số module rất deep (L6.3 LangGraph 18KB, L4.2 Transformer 12KB), một số khá súc tích (L3.3 DL Reg 10KB). Nên balance — hoặc:
- Deep modules chia thành 2 (Part A, Part B)
- Súc tích add thêm examples

Post-audit consensus: current depth chấp nhận được vì mỗi module có nav bottom cho progression. Không cần re-write, chỉ enhance ở gaps.

### 2.4 Missing keywords bạn hỏi

- **multica**: có thể là "Multi-CA" (Multi-Concept Analysis) hoặc typo "MultiCA". Không phải standard term nhưng có concept liên quan: **Mixture of Experts (MoE)**, **Multi-task learning**, **Multi-agent CA (Cognitive Architecture)**. Add tất cả vào glossary.
- **paperclip**: paperclip maximizer thought experiment (Bostrom 2003). Canonical AI alignment problem. Cần bổ sung.
- **speckt**: spec-kit / SpecKit / SDD — Spec-Driven Development. ai_orchestrator có SpecAnalyze + TaskDecompose agents chuyên cái này. Cần module dedicated.

---

## 3. Recommendations

### 3.1 Add Level 8 (AI Artifacts + Landscape)
6 modules mới:
- L8.1 Agents (production sense) — sub-agents, hierarchy, delegation
- L8.2 Skills (Claude Skills format, .claude/skills/, ai_orchestrator uses this)
- L8.3 MCP deep-dive (servers, clients, tools, resources, prompts)
- L8.4 Spec-Driven Development (SpecKit, DoD, Constitution)
- L8.5 AI Alignment (paperclip, instrumental convergence, Constitutional AI deep)
- L8.6 Frameworks survey (LangChain vs LlamaIndex vs DSPy vs Semantic Kernel vs CrewAI vs AutoGen vs Haystack)

### 3.2 Add Glossary
File `glossary.html` với 100+ keywords:
- Core ML/DL/LLM (attention, backprop, RLHF, LoRA)
- Frameworks (LangGraph, DSPy, Semantic Kernel)
- Vector DBs (Pinecone, Qdrant, Weaviate, Milvus, pgvector)
- Alignment (paperclip, corrigibility, mesa-optimization, deceptive alignment)
- Serving (vLLM, TGI, TensorRT-LLM, SGLang)
- Emerging (agentic RAG, MoE, speculative decoding, extended thinking)

### 3.3 Add 50 Interview Q&A
File `interview_50_qa.html`:
- 10 Fundamentals
- 10 Deep Learning
- 10 LLM
- 10 Agents/Systems
- 10 Production/Behavioral

Mỗi câu link về module + evidence.

### 3.4 Minor fixes cho existing modules
- L5.2: fix "35% → 49%" cho contextual retrieval + full stack
- L4.5: clarify QLoRA batch=1 assumption
- L4.2: add BART/mBART/mT5 to encoder-decoder family
- L3.2: note AdamW impl variance across frameworks

---

## 4. Final grade

**Foundation**: A (comprehensive, structured)
**Content accuracy**: A− (5 minor number/formula clarifications needed)
**Coverage of modern AI stack**: B (missing Skills, MCP deep, SDD, Alignment philosophy, frameworks survey)
**Interview readiness**: B+ (add 50 Q&A + Level 8 → A)

**Post-enhance target**: A curriculum ready cho AI Engineer + AI-augmented Dev interviews.

## 5. Execution plan

- [x] Audit written (this file)
- [ ] L8 (6 modules) — ~4h effort compressed
- [ ] glossary.html — ~2h
- [ ] interview_50_qa.html — ~3h
- [ ] Minor fixes ở existing modules — 30 min
- [ ] Update index.html — 15 min

Total: ~10h work compressed into 1 execution session.

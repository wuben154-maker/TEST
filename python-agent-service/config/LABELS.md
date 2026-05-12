---
version: 1.0.0
description: Shared UI labels for multi-language support across Python and TypeScript services
languages:
  - en
  - zh
  - ja
  - ko
---

# Tool Step Labels

These labels are displayed when a specific tool is being executed.

## extract_iocs
- en: Extracting IOCs
- zh: 提取安全指标
- ja: IOCを抽出中
- ko: IOC 추출 중

## decode_base64
- en: Decoding Base64
- zh: 解码 Base64
- ja: Base64をデコード中
- ko: Base64 디코딩 중

## decode_url
- en: URL Decoding
- zh: URL 解码
- ja: URLをデコード中
- ko: URL 디코딩 중

## lookup_threat_intel
- en: Querying Threat Intel
- zh: 查询威胁情报
- ja: 脅威インテリジェンス検索
- ko: 위협 정보 조회 중

## analyze_email_headers
- en: Analyzing Email Headers
- zh: 分析邮件头
- ja: メールヘッダー分析中
- ko: 이메일 헤더 분석 중

## check_sender_reputation
- en: Checking Sender Reputation
- zh: 检查发件人信誉
- ja: 送信者評価確認中
- ko: 발신자 평판 확인 중

## detect_phishing_indicators
- en: Detecting Phishing
- zh: 检测钓鱼特征
- ja: フィッシング検出中
- ko: 피싱 탐지 중

## analyze_pe_header
- en: Analyzing PE Header
- zh: 分析 PE 文件头
- ja: PEヘッダー分析中
- ko: PE 헤더 분석 중

## extract_strings
- en: Extracting Strings
- zh: 提取字符串
- ja: 文字列抽出中
- ko: 문자열 추출 중

## detect_packer
- en: Detecting Packer
- zh: 检测加壳
- ja: パッカー検出中
- ko: 패커 탐지 중

## check_file_hash
- en: Checking Malware DB
- zh: 查询恶意软件库
- ja: マルウェアDB照会中
- ko: 악성코드 DB 조회 중

## analyze_http_request
- en: Analyzing HTTP Request
- zh: 分析 HTTP 请求
- ja: HTTPリクエスト分析中
- ko: HTTP 요청 분석 중

## detect_web_attack
- en: Detecting Web Attack
- zh: 检测 Web 攻击
- ja: Web攻撃検出中
- ko: 웹 공격 탐지 중

## analyze_javascript
- en: Analyzing JavaScript
- zh: 分析 JavaScript
- ja: JavaScript分析中
- ko: JavaScript 분석 중

## correlate_alerts
- en: Correlating Alerts
- zh: 关联告警
- ja: アラート相関分析中
- ko: 알림 상관관계 분석 중

## assess_severity
- en: Assessing Severity
- zh: 评估严重性
- ja: 重大度評価中
- ko: 심각도 평가 중

## check_false_positive
- en: Checking False Positive
- zh: 检查误报
- ja: 誤検知確認中
- ko: 오탐 확인 중

## lookup_cve
- en: Looking up CVE
- zh: 查询 CVE
- ja: CVE照会中
- ko: CVE 조회 중

## assess_exploitability
- en: Assessing Exploitability
- zh: 评估可利用性
- ja: 悪用可能性評価中
- ko: 취약점 평가 중

## prioritize_patches
- en: Prioritizing Patches
- zh: 确定补丁优先级
- ja: パッチ優先順位決定中
- ko: 패치 우선순위 결정 중

## generate_report
- en: Generating Report
- zh: 生成分析报告
- ja: レポート生成中
- ko: 보고서 생성 중

## write_todos
- en: Creating Task Plan
- zh: 创建任务计划
- ja: タスクプラン作成中
- ko: 작업 계획 생성 중

## read_todos
- en: Reading Tasks
- zh: 读取任务列表
- ja: タスク読み込み中
- ko: 작업 읽기 중

## update_todo
- en: Updating Task Status
- zh: 更新任务状态
- ja: タスク状態更新中
- ko: 작업 상태 업데이트 중

## add_note
- en: Adding Task Note
- zh: 添加任务备注
- ja: タスクメモ追加中
- ko: 작업 메모 추가 중

## ls
- en: Browsing Files
- zh: 浏览文件目录
- ja: ファイル一覧表示中
- ko: 파일 목록 조회 중

## read_file
- en: Reading File
- zh: 读取文件内容
- ja: ファイル読み込み中
- ko: 파일 읽기 중

## write_file
- en: Writing File
- zh: 写入文件
- ja: ファイル書き込み中
- ko: 파일 쓰기 중

## edit_file
- en: Editing File
- zh: 编辑文件
- ja: ファイル編集中
- ko: 파일 편집 중

## glob
- en: Searching Files
- zh: 搜索文件
- ja: ファイル検索中
- ko: 파일 검색 중

## grep
- en: Searching Content
- zh: 搜索内容
- ja: コンテンツ検索中
- ko: 콘텐츠 검색 중

## task
- en: Executing Subtask
- zh: 执行子任务
- ja: サブタスク実行中
- ko: 서브 작업 실행 중

---

# Analysis Phases

These labels describe the current phase of the analysis workflow.

## phase_1
- en: 🔍 Understanding input content
- zh: 🔍 理解输入内容
- ja: 🔍 入力内容を理解中
- ko: 🔍 입력 내용 이해 중

## phase_2
- en: 🧩 Extracting security indicators
- zh: 🧩 提取安全指标
- ja: 🧩 セキュリティ指標を抽出中
- ko: 🧩 보안 지표 추출 중

## phase_3
- en: 🔐 Decoding obfuscated content
- zh: 🔐 解码混淆内容
- ja: 🔐 難読化コンテンツをデコード中
- ko: 🔐 난독화된 콘텐츠 디코딩 중

## phase_4
- en: 🌐 Cross-referencing threat intelligence
- zh: 🌐 关联威胁情报
- ja: 🌐 脅威インテリジェンスと照合中
- ko: 🌐 위협 인텔리전스 참조 중

## phase_5
- en: 📊 Correlating attack patterns
- zh: 📊 分析攻击模式
- ja: 📊 攻撃パターンを分析中
- ko: 📊 공격 패턴 분석 중

## phase_6
- en: 🎯 Assessing risk severity
- zh: 🎯 评估风险等级
- ja: 🎯 リスク重大度を評価中
- ko: 🎯 위험 심각도 평가 중

## phase_7
- en: 📝 Compiling findings
- zh: 📝 汇总分析发现
- ja: 📝 発見事項を整理中
- ko: 📝 분석 결과 정리 중

## phase_8
- en: ✅ Finalizing analysis
- zh: ✅ 完成分析验证
- ja: ✅ 分析を完了中
- ko: ✅ 분석 완료 중

## phase_9
- en: 🔄 Deep verification
- zh: 🔄 深度验证确认
- ja: 🔄 深層検証中
- ko: 🔄 심층 검증 중

## phase_10
- en: 📋 Generating report
- zh: 📋 生成分析报告
- ja: 📋 レポートを生成中
- ko: 📋 보고서 생성 중

---

# UI Text

Common UI text used across the application.

## connecting
- en: Connecting to DeepAgent
- zh: 连接 DeepAgent 服务
- ja: DeepAgentに接続中
- ko: DeepAgent에 연결 중

## initEngine
- en: Initializing Analysis Engine
- zh: 初始化分析引擎
- ja: 分析エンジンを初期化中
- ko: 분석 엔진 초기화 중

## engineReady
- en: Analysis Engine Ready
- zh: 分析引擎就绪
- ja: 分析エンジン準備完了
- ko: 분석 엔진 준비 완료

## analyzing
- en: Analyzing security data
- zh: 分析安全数据
- ja: セキュリティデータを分析中
- ko: 보안 데이터 분석 중

## analysisDone
- en: ✨ Analysis complete
- zh: ✨ 分析完成
- ja: ✨ 分析完了
- ko: ✨ 분석 완료

## analysisFailed
- en: Analysis failed
- zh: 分析失败
- ja: 分析失敗
- ko: 분석 실패

## aiError
- en: AI service error
- zh: AI 服务错误
- ja: AIサービスエラー
- ko: AI 서비스 오류

## rateLimited
- en: Rate limited, please retry later
- zh: 请求过于频繁
- ja: レート制限中、後で再試行してください
- ko: 속도 제한됨, 나중에 다시 시도하세요

## quotaExceeded
- en: Quota exceeded
- zh: 额度不足
- ja: クォータ超過
- ko: 할당량 초과

## usingDeepAgent
- en: 🚀 Connected to DeepAgent Intelligence
- zh: 🚀 已连接 DeepAgent 智能分析
- ja: 🚀 DeepAgentインテリジェンスに接続済み
- ko: 🚀 DeepAgent 인텔리전스에 연결됨

## usingFallback
- en: ⚡ Using Local Analysis Engine
- zh: ⚡ 使用本地分析引擎
- ja: ⚡ ローカル分析エンジンを使用中
- ko: ⚡ 로컬 분석 엔진 사용 중

## fallbackReason
- en: "Reason:"
- zh: "原因:"
- ja: "理由:"
- ko: "이유:"

## thinking
- en: Thinking...
- zh: 思考中...
- ja: 思考中...
- ko: 생각 중...

## analysisComplete
- en: Analysis complete
- zh: 分析完成
- ja: 分析完了
- ko: 분석 완료

## startingAgent
- en: Starting
- zh: 启动
- ja: 開始中
- ko: 시작 중

## agentReady
- en: ready
- zh: 已就绪
- ja: 準備完了
- ko: 준비 완료

## analysisTimeMsg
- en: Analysis complete, took
- zh: 分析完成，耗时
- ja: 分析完了、所要時間
- ko: 분석 완료, 소요 시간

## seconds
- en: seconds
- zh: 秒
- ja: 秒
- ko: 초

## requestTooFrequent
- en: Request too frequent, please try again later
- zh: 请求过于频繁，请稍后再试
- ja: リクエストが頻繁すぎます、後でもう一度お試しください
- ko: 요청이 너무 빈번합니다, 나중에 다시 시도하세요

## insufficientCredits
- en: Insufficient credits, please recharge
- zh: 额度不足，请充值
- ja: クレジット不足、チャージしてください
- ko: 크레딧 부족, 충전해 주세요

## analysisError
- en: Analysis error occurred
- zh: 分析过程中发生错误
- ja: 分析エラーが発生しました
- ko: 분석 오류가 발생했습니다

## securityContent
- en: Security content
- zh: 安全内容
- ja: セキュリティコンテンツ
- ko: 보안 콘텐츠

## aiAnalysis
- en: AI analysis
- zh: AI 分析
- ja: AI分析
- ko: AI 분석

## provideSpecificContent
- en: Unable to identify specific security data type. Please provide more specific security content (such as email headers, logs, vulnerability reports) for in-depth analysis.
- zh: 无法识别具体的安全数据类型。请提供更具体的安全内容（如邮件头、日志、漏洞报告）以进行深入分析。
- ja: 具体的なセキュリティデータタイプを識別できません。詳細な分析のために、より具体的なセキュリティコンテンツ（メールヘッダー、ログ、脆弱性レポートなど）を提供してください。
- ko: 구체적인 보안 데이터 유형을 식별할 수 없습니다. 심층 분석을 위해 더 구체적인 보안 콘텐츠(이메일 헤더, 로그, 취약점 보고서 등)를 제공해 주세요.

## executingSubtask
- en: Executing Subtask
- zh: 执行子任务
- ja: サブタスク実行中
- ko: 서브 작업 실행 중

---

# Stream Adapter

Labels for deepagents_stream_adapter SSE events. User-visible text must be loaded from here.

## stream_analysis_start
- en: Starting analysis...
- zh: 开始分析...
- ja: 分析を開始...
- ko: 분석 시작...

## stream_analysis_complete
- en: Analysis Complete
- zh: 分析完成
- ja: 分析完了
- ko: 분석 완료

## stream_hitl_waiting
- en: Waiting for your input
- zh: 等待人工确认或输入
- ja: 入力待ち
- ko: 사용자 입력 대기

## research_trace_title
- en: Research Execution Trace
- zh: 研究执行追踪
- ja: 研究実行トレース
- ko: 연구 실행 추적

## research_trace_col_round
- en: Round
- zh: 轮次
- ja: ラウンド
- ko: 라운드

## research_trace_col_agent
- en: Agent
- zh: 代理
- ja: エージェント
- ko: 에이전트

## research_trace_col_step
- en: Step
- zh: 步骤
- ja: ステップ
- ko: 단계

## research_trace_col_action
- en: Action
- zh: 动作
- ja: アクション
- ko: 작업

## research_trace_col_insight
- en: Round Insight
- zh: 轮次结论
- ja: ラウンド結論
- ko: 라운드 결론

## research_trace_col_elapsed
- en: Duration(ms)
- zh: 耗时(ms)
- ja: 所要時間(ms)
- ko: 소요시간(ms)

## research_trace_col_prompt
- en: Prompt
- zh: 输入
- ja: 入力
- ko: 입력

## research_trace_col_completion
- en: Completion
- zh: 输出
- ja: 出力
- ko: 출력

## research_trace_col_total
- en: Total
- zh: 总计
- ja: 合計
- ko: 총계

## research_trace_action_fallback
- en: Reasoning trace
- zh: 思考追踪
- ja: 思考トレース
- ko: 추론 추적

## research_trace_agent_main
- en: Main Agent
- zh: 主Agent
- ja: メインエージェント
- ko: 메인 에이전트

## research_trace_agent_sub
- en: Sub Agent
- zh: 子Agent
- ja: サブエージェント
- ko: 하위 에이전트

## research_trace_total_prompt
- en: Total prompt tokens
- zh: 总输入 tokens
- ja: 入力トークン合計
- ko: 입력 토큰 합계

## research_trace_total_completion
- en: Total completion tokens
- zh: 总输出 tokens
- ja: 出力トークン合計
- ko: 출력 토큰 합계

## research_trace_total_tokens
- en: Total tokens
- zh: 总 tokens
- ja: 総トークン数
- ko: 총 토큰 수

## research_trace_no_internal_data
- en: Internal graph details unavailable; emitted minimal trace.
- zh: 图内细节不可用；已输出最小追踪信息。
- ja: 内部グラフ詳細を取得できないため、最小トレースを出力しました。
- ko: 내부 그래프 상세 정보를 가져올 수 없어 최소 추적만 출력했습니다.

## research_final_result_title
- en: Final Result
- zh: 最终结果
- ja: 最終結果
- ko: 최종 결과

## research_final_result_missing
- en: No final result was generated by the research graph.
- zh: 研究图未生成最终结果。
- ja: 研究グラフは最終結果を生成しませんでした。
- ko: 연구 그래프가 최종 결과를 생성하지 못했습니다.

## research_sse_phase_clarify
- en: Clarify research request
- zh: 研究信息澄清
- ja: 研究依頼の確認
- ko: 연구 요청 확인

## research_sse_phase_brief
- en: Define research brief
- zh: 拟定研究课题
- ja: 研究ブリーフの作成
- ko: 연구 과제 정리

## research_sse_phase_collect
- en: Gather research material
- zh: 收集研究材料
- ja: 調査材料の収集
- ko: 연구 자료 수집

## research_sse_phase_final
- en: Write final report
- zh: 整理成稿
- ja: 最終レポート作成
- ko: 최종 보고서 작성

## research_sse_phase_step
- en: Research step
- zh: 研究步骤
- ja: 研究ステップ
- ko: 연구 단계

## research_sse_human_input
- en: Input
- zh: 输入
- ja: 入力
- ko: 입력

## research_sse_prefix_thinking
- en: "[Thinking]"
- zh: "【思考】"
- ja: "【思考】"
- ko: "[사고]"

## research_sse_prefix_answer
- en: "[Answer]"
- zh: "【说明】"
- ja: "【回答】"
- ko: "[설명]"

## research_sse_prefix_draft_findings
- en: "[Research draft — not the final deliverable]"
- zh: "【研究草稿 — 非最终交付稿】"
- ja: "【研究ドラフト — 最終成果ではありません】"
- ko: "[연구 초안 — 최종 결과 아님]"

## research_sse_prefix_final_prep
- en: "[Final report — model notes]"
- zh: "【终稿撰写 — 模型说明】"
- ja: "【最終レポート — モデルメモ】"
- ko: "[최종 보고서 — 모델 메모]"

## stream_subagent_analyzing
- en: analyzing...
- zh: 分析中...
- ja: 分析中...
- ko: 분석 중...

## stream_subagent_complete
- en: complete
- zh: 完成
- ja: 完了
- ko: 완료

## task_submitted_placeholder
- en: task submitted
- zh: 任务已提交
- ja: タスクを送信しました
- ko: 작업이 제출되었습니다

## stream_missing_subagent_outputs
- en: Missing subagent outputs
- zh: 缺少子代理输出
- ja: サブエージェント出力がありません
- ko: 하위 에이전트 출력 없음

## stream_missing_subagent_detail
- en: Missing subagent outputs: no non-empty task tool results were produced.
- zh: 缺少子代理输出：未产生非空的任务工具结果。
- ja: サブエージェント出力がありません：空でないタスクツール結果が生成されませんでした。
- ko: 하위 에이전트 출력 없음: 비어 있지 않은 작업 도구 결과가 생성되지 않았습니다.

## stream_subagent_bypass_label
- en: Sub-Agent bypass detected
- zh: 检测到子代理绕过
- ja: サブエージェントバイパスを検出
- ko: 하위 에이전트 우회 감지됨

## stream_subagent_bypass_detail
- en: Main agent called tools but did not delegate via task(). Result may lack specialized sub-agent analysis.
- zh: 主代理调用了工具但未通过 task() 委托。结果可能缺少专业子代理分析。
- ja: メインエージェントがツールを呼び出しましたが、task() で委任していません。結果に専門サブエージェント分析が含まれない可能性があります。
- ko: 메인 에이전트가 도구를 호출했지만 task()를 통해 위임하지 않았습니다. 결과에 전문 하위 에이전트 분석이 누락될 수 있습니다.

## stream_skill_completed
- en: Completed
- zh: 已完成
- ja: 完了
- ko: 완료

## stream_skill_completed_suffix
- en: completed
- zh: 已完成
- ja: 完了
- ko: 완료

## stream_task_completed_fallback
- en: Task completed.
- zh: 任务已完成。
- ja: タスクが完了しました。
- ko: 작업이 완료되었습니다。

---

# Intent Understanding

Labels for intent understanding and context summary functionality.

## context_no_history
- en: This is a new conversation with no history.
- zh: 这是新对话，没有历史上下文。
- ja: これは新しい会話で、履歴がありません。
- ko: 이것은 기록이 없는 새로운 대화입니다。

## context_key_entities
- en: Key entities
- zh: 关键实体
- ja: 主要エンティティ
- ko: 주요 엔티티

## context_analyzed_files
- en: Analyzed files
- zh: 已分析文件
- ja: 分析済みファイル
- ko: 분석된 파일

## context_user_preferences
- en: User preferences
- zh: 用户偏好
- ja: ユーザー設定
- ko: 사용자 기본 설정

## context_recent_interactions
- en: Recent interactions
- zh: 最近交互
- ja: 最近の対話
- ko: 최근 상호작용

## context_conversation_history
- en: Conversation history
- zh: 会话历史
- ja: 会話履歴
- ko: 대화 기록

## context_user_label
- en: User
- zh: 用户
- ja: ユーザー
- ko: 사용자

## context_language_label
- en: Language
- zh: 语言
- ja: 言語
- ko: 언어

## context_common_task_type
- en: Common task type
- zh: 常用任务类型
- ja: 一般的なタスクタイプ
- ko: 일반 작업 유형

## context_no_results
- en: No analysis results found
- zh: 未找到分析结果
- ja: 分析結果が見つかりません
- ko: 분석 결과를 찾을 수 없습니다

## merge_report_title
- en: Merged Analysis Report
- zh: 合并分析报告
- ja: 統合分析レポート
- ko: 통합 분석 보고서

## merge_report_summary
- en: Summary
- zh: 摘要
- ja: サマリー
- ko: 요약

## merge_report_section
- en: Analysis Result
- zh: 分析结果
- ja: 分析結果
- ko: 분석 결과

## intent_no_context
- en: No session history.
- zh: 无历史上下文
- ja: セッション履歴なし
- ko: 세션 기록 없음

## intent_cannot_understand
- en: Unable to understand your request. Please provide more details.
- zh: 无法理解您的请求，请提供更多详细信息。
- ja: リクエストを理解できません。詳細を提供してください。
- ko: 요청을 이해할 수 없습니다. 자세한 내용을 제공해 주세요.

## intent_context_enriched
- en: Context enriched
- zh: 上下文已增强
- ja: コンテキストが強化されました
- ko: 컨텍스트가 강화되었습니다

## clarification_low_confidence
- en: I'm not entirely sure what you're asking for. Could you please clarify:
- zh: 我不太确定您的具体需求，能否请您澄清：
- ja: ご要望が明確でないため、以下についてご確認いただけますか：
- ko: 요청사항이 명확하지 않아 다음 사항을 확인해 주시겠습니까:

## clarification_ambiguous_category
- en: I detected multiple possible task types. Which one do you need?
- zh: 我检测到多种可能的任务类型，您需要哪一种？
- ja: 複数のタスクタイプが検出されました。どちらが必要ですか？
- ko: 여러 작업 유형이 감지되었습니다. 어떤 것이 필요하신가요?

## clarification_missing_details
- en: To better help you, I need more information:
- zh: 为了更好地帮助您，我需要更多信息：
- ja: より適切にサポートするため、追加情報が必要です：
- ko: 더 나은 지원을 위해 추가 정보가 필요합니다:

## intent_out_of_scope
- en: This request is outside my capabilities. I specialize in security analysis, threat detection, and related research tasks. Please provide a security-related request or ask about previous analysis results.
- zh: 此请求超出我的能力范围。我专注于安全分析、威胁检测和相关研究任务。请提供与安全相关的请求或询问之前的分析结果。
- ja: このリクエストは私の能力範囲外です。私はセキュリティ分析、脅威検出、関連する研究タスクに特化しています。セキュリティ関連のリクエストを提供するか、以前の分析結果について尋ねてください。
- ko: 이 요청은 제 능력 범위를 벗어났습니다. 저는 보안 분석, 위협 탐지 및 관련 연구 작업에 특화되어 있습니다. 보안 관련 요청을 제공하거나 이전 분석 결과에 대해 문의해 주세요.

## intent_unrelated_input
- en: I couldn't find any security-related content in your request. I specialize in security analysis and threat detection. Could you please provide a security-related request?
- zh: 我在您的请求中找不到任何与安全相关的内容。我专注于安全分析和威胁检测。请提供与安全相关的请求。
- ja: リクエストにセキュリティ関連のコンテンツが見つかりませんでした。私はセキュリティ分析と脅威検出に特化しています。セキュリティ関連のリクエストを提供してください。
- ko: 요청에서 보안 관련 내용을 찾을 수 없습니다. 저는 보안 분석 및 위협 탐지에 특화되어 있습니다. 보안 관련 요청을 제공해 주세요.

## intent_language_instruction
- en: IMPORTANT: You MUST respond in English. All summaries, analysis goals, and approaches must be written in English.
- zh: 重要：你必须使用中文进行回复。所有摘要、分析目标和方法都必须使用中文撰写。
- ja: 重要：必ず日本語で回答してください。すべての要約、分析目標、アプローチは日本語で記述する必要があります。
- ko: 중요: 반드시 한국어로 응답해야 합니다. 모든 요약, 분석 목표 및 접근 방식은 한국어로 작성되어야 합니다.

## intent_service_error
- en: Unable to understand request due to service error
- zh: 由于服务错误，无法理解请求
- ja: サービスエラーのため、リクエストを理解できませんでした
- ko: 서비스 오류로 인해 요청을 이해할 수 없습니다

## intent_service_unavailable
- en: Service temporarily unavailable. Please try again.
- zh: 服务暂时不可用，请稍后重试。
- ja: サービスが一時的に利用できません。後でもう一度お試しください。
- ko: 서비스가 일시적으로 사용할 수 없습니다. 나중에 다시 시도해 주세요.

## intent_analysis_failed
- en: Intent analysis failed; continuing with analysis.
- zh: 意图分析失败；将继续进行分析。
- ja: 意図解析に失敗しましたが、分析を続行します。
- ko: 의도 분석에 실패했지만 분석을 계속 진행합니다.

## intent_step_understanding
- en: Intent Understanding
- zh: 意图理解
- ja: 意図理解
- ko: 의도 이해

## intent_step_deep_understanding
- en: Deep Understanding
- zh: 深度理解
- ja: 深層理解
- ko: 심층 이해

## out_of_scope_notice_label
- en: Capability Notice
- zh: 能力范围提示
- ja: 対応範囲のお知らせ
- ko: 기능 범위 안내

## unknown_task_notice_label
- en: Task Scope Notice
- zh: 任务范围提示
- ja: タスク範囲通知
- ko: 작업 범위 알림

## unknown_task_notice_detail
- en: In addition to security event handling, I can also help with deep research. Please provide more details.
- zh: 除了安全事件处理，我还可以帮你做深度研究工作，请输入更详细的需求。
- ja: セキュリティイベント処理に加えて、深層研究もお手伝いできます。詳細を入力してください。
- ko: 보안 이벤트 처리 외에도 심층 연구를 도와드릴 수 있습니다. 자세한 내용을 입력해 주세요.

## option_prefix
- en: Option
- zh: 选项
- ja: オプション
- ko: 옵션

## stream_error_label
- en: Analysis failed
- zh: 分析失败
- ja: 分析に失敗しました
- ko: 분석 실패

## stream_error_unknown
- en: Unknown error (check backend logs)
- zh: 未知错误（请查看后端日志）
- ja: 不明なエラー（バックエンドログを確認してください）
- ko: 알 수 없는 오류(백엔드 로그 확인)

## simple_analysis_title
- en: Security analysis result
- zh: 安全分析结果
- ja: セキュリティ分析結果
- ko: 보안 분석 결과

## simple_analysis_summary_template
- en: "Found {ips} IPs, {urls} URLs, {domains} domains, {hashes} hashes"
- zh: "发现 {ips} 个IP，{urls} 个URL，{domains} 个域名，{hashes} 个哈希"
- ja: "{ips} 個のIP、{urls} 個のURL、{domains} 個のドメイン、{hashes} 個のハッシュを検出"
- ko: "IP {ips}개, URL {urls}개, 도메인 {domains}개, 해시 {hashes}개 발견"

## simple_step_init_label
- en: Initialize simple analysis mode
- zh: 初始化简单分析模式
- ja: シンプル分析モードを初期化
- ko: 단순 분석 모드 초기화

## simple_step_ready_label
- en: Simple analysis mode ready
- zh: 简单分析模式就绪
- ja: シンプル分析モード準備完了
- ko: 단순 분석 모드 준비 완료

## simple_step_ready_detail
- en: LangGraph disabled. Running fast IOC extraction.
- zh: 未使用 LangGraph，执行快速 IOC 提取。
- ja: LangGraphを無効化し、高速IOC抽出を実行します。
- ko: LangGraph 비활성화 상태에서 빠른 IOC 추출을 수행합니다.

## simple_step_extract_label
- en: Extract IOCs
- zh: 提取 IOC
- ja: IOCを抽出
- ko: IOC 추출

## simple_step_extract_detail_template
- en: "Found {ips} IPs, {urls} URLs"
- zh: "发现 {ips} 个IP，{urls} 个URL"
- ja: "{ips} 個のIP、{urls} 個のURLを検出"
- ko: "IP {ips}개, URL {urls}개 발견"

## simple_conclusion_header
- en: "## Analysis Result"
- zh: "## 分析结果"
- ja: "## 分析結果"
- ko: "## 분석 결과"

## simple_conclusion_severity
- en: Severity
- zh: 严重程度
- ja: 重大度
- ko: 심각도

## simple_conclusion_summary
- en: Summary
- zh: 摘要
- ja: 要約
- ko: 요약

## simple_conclusion_entities_header
- en: "### Entities Found"
- zh: "### 发现的实体"
- ja: "### 検出されたエンティティ"
- ko: "### 탐지된 엔티티"

## simple_entity_ip
- en: IP
- zh: IP
- ja: IP
- ko: IP

## simple_entity_url
- en: URL
- zh: URL
- ja: URL
- ko: URL

## simple_entity_domain
- en: Domain
- zh: 域名
- ja: ドメイン
- ko: 도메인

## simple_entity_hash
- en: Hash
- zh: 哈希
- ja: ハッシュ
- ko: 해시

## simple_entity_email
- en: Email
- zh: 邮箱
- ja: メール
- ko: 이메일

## simple_done_detail_template
- en: "Simple analysis completed in {seconds}s"
- zh: "简单模式分析完成，耗时 {seconds} 秒"
- ja: "シンプル分析が完了しました（{seconds}秒）"
- ko: "단순 분석 완료 ({seconds}초)"

## planner_planning
- en: Planning tasks
- zh: 规划任务
- ja: タスク計画中
- ko: 작업 계획 중

## planner_single_task
- en: Single task identified
- zh: 识别为单一任务
- ja: 単一タスクを識別
- ko: 단일 작업 식별됨

## planner_multi_task
- en: tasks planned
- zh: 个任务已规划
- ja: タスクを計画
- ko: 작업 계획됨

## planner_executing
- en: Executing
- zh: 正在执行
- ja: 実行中
- ko: 실행 중

## planner_completed
- en: Completed
- zh: 已完成
- ja: 完了
- ko: 완료

## planner_failed
- en: Failed
- zh: 执行失败
- ja: 失敗
- ko: 실패

## planner_security_task
- en: Security Analysis
- zh: 安全分析
- ja: セキュリティ分析
- ko: 보안 분석

## planner_research_task
- en: Research Task
- zh: 研究任务
- ja: 研究タスク
- ko: 연구 작업

## analysis_in_progress
- en: Analysis in progress
- zh: 分析中
- ja: 分析中
- ko: 분석 중

## report_title
- en: "# 📋 Analysis Report"
- zh: "# 📋 分析报告"
- ja: "# 📋 分析レポート"
- ko: "# 📋 분석 보고서"

## report_summary_header
- en: "## 📊 Executive Summary"
- zh: "## 📊 执行摘要"
- ja: "## 📊 エグゼクティブサマリー"
- ko: "## 📊 요약"

## report_tasks_completed
- en: Tasks Completed
- zh: 已完成任务
- ja: 完了したタスク
- ko: 완료된 작업

## report_security_section
- en: "## 🔒 Security Analysis"
- zh: "## 🔒 安全分析"
- ja: "## 🔒 セキュリティ分析"
- ko: "## 🔒 보안 분석"

## report_research_section
- en: "## 🔍 Research Findings"
- zh: "## 🔍 研究发现"
- ja: "## 🔍 調査結果"
- ko: "## 🔍 연구 결과"

## report_general_section
- en: "## 📝 Analysis Results"
- zh: "## 📝 分析结果"
- ja: "## 📝 分析結果"
- ko: "## 📝 분석 결과"

## report_default_security_title
- en: Security Analysis
- zh: 安全分析
- ja: セキュリティ分析
- ko: 보안 분석

## report_default_research_title
- en: Research
- zh: 研究
- ja: 調査
- ko: 연구

## report_default_general_title
- en: Analysis
- zh: 分析
- ja: 分析
- ko: 분석

## planner_analyzing
- en: Analyzing request complexity
- zh: 分析请求复杂度
- ja: リクエストの複雑さを分析中
- ko: 요청 복잡도 분석 중

## planner_decomposing
- en: Decomposing into subtasks
- zh: 拆分为子任务
- ja: サブタスクに分解中
- ko: 하위 작업으로 분해 중

## clarification_what_task
- en: What specific task do you want to accomplish?
- zh: 您想要完成什么具体任务？
- ja: どのような具体的なタスクを実行したいですか？
- ko: 어떤 구체적인 작업을 수행하고 싶으신가요?

## clarification_task_type
- en: What type of analysis or task do you need? (e.g., security analysis, research, code review)
- zh: 您需要什么类型的分析或任务？（例如：安全分析、研究、代码审查）
- ja: どのようなタイプの分析やタスクが必要ですか？（例：セキュリティ分析、研究、コードレビュー）
- ko: 어떤 유형의 분석이나 작업이 필요하신가요? (예: 보안 분석, 연구, 코드 검토)

## clarification_security_type
- en: What type of security analysis? (e.g., malware analysis, email security, vulnerability scan)
- zh: 需要什么类型的安全分析？（例如：恶意软件分析、邮件安全、漏洞扫描）
- ja: どのようなタイプのセキュリティ分析ですか？（例：マルウェア分析、メールセキュリティ、脆弱性スキャン）
- ko: 어떤 유형의 보안 분석인가요? (예: 멀웨어 분석, 이메일 보안, 취약점 스캔)

## clarification_research_topic
- en: What topic or question do you want to research?
- zh: 您想研究什么主题或问题？
- ja: どのトピックや質問を調査したいですか？
- ko: 어떤 주제나 질문을 연구하고 싶으신가요?

## clarification_files_focus
- en: What should I focus on in these files? (e.g., security threats, code quality, data extraction)
- zh: 我应该关注这些文件的哪些方面？（例如：安全威胁、代码质量、数据提取）
- ja: これらのファイルのどの側面に焦点を当てるべきですか？（例：セキュリティ脅威、コード品質、データ抽出）
- ko: 이러한 파일의 어떤 측면에 집중해야 하나요? (예: 보안 위협, 코드 품질, 데이터 추출)

---

# File Parsing

Labels for file parsing and analysis output messages.

## file_binary
- en: Binary file
- zh: 二进制文件
- ja: バイナリファイル
- ko: 바이너리 파일

## file_filename
- en: Filename
- zh: 文件名
- ja: ファイル名
- ko: 파일명

## file_type
- en: Type
- zh: 类型
- ja: タイプ
- ko: 유형

## file_size
- en: Size
- zh: 大小
- ja: サイズ
- ko: 크기

## file_bytes
- en: bytes
- zh: 字节
- ja: バイト
- ko: 바이트

## file_error
- en: Error
- zh: 错误
- ja: エラー
- ko: 오류

## file_pcap_analysis
- en: PCAP Network Packet Analysis
- zh: PCAP 网络包分析
- ja: PCAPネットワークパケット分析
- ko: PCAP 네트워크 패킷 분석

## file_pcap_total_packets
- en: Total packets
- zh: 总包数
- ja: 総パケット数
- ko: 총 패킷 수

## file_pcap_statistics
- en: Statistics
- zh: 统计信息
- ja: 統計情報
- ko: 통계 정보

## file_pcap_ip_packets
- en: IP packets
- zh: IP 包
- ja: IPパケット
- ko: IP 패킷

## file_pcap_tcp_packets
- en: TCP packets
- zh: TCP 包
- ja: TCPパケット
- ko: TCP 패킷

## file_pcap_udp_packets
- en: UDP packets
- zh: UDP 包
- ja: UDPパケット
- ko: UDP 패킷

## file_pcap_dns_packets
- en: DNS packets
- zh: DNS 包
- ja: DNSパケット
- ko: DNS 패킷

## file_pcap_src_ip_count
- en: Source IP count
- zh: 源 IP 数
- ja: 送信元IP数
- ko: 소스 IP 수

## file_pcap_dst_ip_count
- en: Destination IP count
- zh: 目标 IP 数
- ja: 宛先IP数
- ko: 대상 IP 수

## file_pcap_src_ips
- en: Source IP addresses
- zh: 源 IP 地址
- ja: 送信元IPアドレス
- ko: 소스 IP 주소

## file_pcap_dst_ips
- en: Destination IP addresses
- zh: 目标 IP 地址
- ja: 宛先IPアドレス
- ko: 대상 IP 주소

## file_pcap_sample_note
- en: Note: Only analyzed first {sample_size} packets out of {total} total packets
- zh: 注意: 仅分析了前 {sample_size} 个包，共 {total} 个包
- ja: 注意: 最初の {sample_size} パケットのみ分析しました（合計 {total} パケット）
- ko: 참고: 처음 {sample_size}개 패킷만 분석했습니다 (총 {total}개 패킷)

## file_pcap_requires_lib
- en: PCAP file - requires scapy library
- zh: PCAP 文件 - 需要 scapy 库
- ja: PCAPファイル - scapyライブラリが必要です
- ko: PCAP 파일 - scapy 라이브러리가 필요합니다

## file_pcap_install_note
- en: Note: Install scapy library to enable PCAP parsing
- zh: 注意: 安装 scapy 库以启用 PCAP 解析功能
- ja: 注意: scapyライブラリをインストールしてPCAP解析機能を有効にしてください
- ko: 참고: scapy 라이브러리를 설치하여 PCAP 파싱 기능을 활성화하세요

## file_pcap_parse_failed
- en: PCAP parsing failed
- zh: PCAP 解析失败
- ja: PCAP解析に失敗しました
- ko: PCAP 파싱 실패

## file_pe_analysis
- en: PE Executable Analysis
- zh: PE 可执行文件分析
- ja: PE実行可能ファイル分析
- ko: PE 실행 파일 분석

## file_pe_architecture
- en: Architecture
- zh: 架构
- ja: アーキテクチャ
- ko: 아키텍처

## file_pe_timestamp
- en: Timestamp
- zh: 时间戳
- ja: タイムスタンプ
- ko: 타임스탬프

## file_pe_imported_dlls
- en: Imported DLLs
- zh: 导入的 DLL
- ja: インポートされたDLL
- ko: 가져온 DLL

## file_pe_exported_functions
- en: Exported functions
- zh: 导出的函数
- ja: エクスポートされた関数
- ko: 내보낸 함수

## file_pe_sections
- en: Sections
- zh: 节信息
- ja: セクション情報
- ko: 섹션 정보

## file_pe_requires_lib
- en: PE file - requires pefile library
- zh: PE 文件 - 需要 pefile 库
- ja: PEファイル - pefileライブラリが必要です
- ko: PE 파일 - pefile 라이브러리가 필요합니다

## file_pe_install_note
- en: Note: Install pefile library to enable PE parsing
- zh: 注意: 安装 pefile 库以启用 PE 解析功能
- ja: 注意: pefileライブラリをインストールしてPE解析機能を有効にしてください
- ko: 참고: pefile 라이브러리를 설치하여 PE 파싱 기능을 활성화하세요

## file_pe_parse_failed
- en: PE parsing failed
- zh: PE 解析失败
- ja: PE解析に失敗しました
- ko: PE 파싱 실패

## file_elf_analysis
- en: ELF Executable Analysis
- zh: ELF 可执行文件分析
- ja: ELF実行可能ファイル分析
- ko: ELF 실행 파일 분석

## file_elf_sections
- en: Sections
- zh: 节信息
- ja: セクション情報
- ko: 섹션 정보

## file_elf_symbol_table
- en: Symbol table
- zh: 符号表
- ja: シンボルテーブル
- ko: 심볼 테이블

## file_elf_requires_lib
- en: ELF file - requires pyelftools library
- zh: ELF 文件 - 需要 pyelftools 库
- ja: ELFファイル - pyelftoolsライブラリが必要です
- ko: ELF 파일 - pyelftools 라이브러리가 필요합니다

## file_elf_install_note
- en: Note: Install pyelftools library to enable ELF parsing
- zh: 注意: 安装 pyelftools 库以启用 ELF 解析功能
- ja: 注意: pyelftoolsライブラリをインストールしてELF解析機能を有効にしてください
- ko: 참고: pyelftools 라이브러리를 설치하여 ELF 파싱 기능을 활성화하세요

## file_elf_parse_failed
- en: ELF parsing failed
- zh: ELF 解析失败
- ja: ELF解析に失敗しました
- ko: ELF 파싱 실패

## file_archive_analysis
- en: Archive file
- zh: 压缩文件
- ja: アーカイブファイル
- ko: 아카이브 파일

## file_archive_file_count
- en: File count
- zh: 文件数
- ja: ファイル数
- ko: 파일 수

## file_archive_file_list
- en: File list
- zh: 文件列表
- ja: ファイルリスト
- ko: 파일 목록

## file_archive_more_files
- en: ... {count} more files
- zh: ... 还有 {count} 个文件
- ja: ... あと {count} 個のファイル
- ko: ... {count}개 더 있음

## file_archive_unsupported_format
- en: Note: Detailed parsing for this archive format is not supported
- zh: 注意: 暂不支持此压缩格式的详细解析
- ja: 注意: このアーカイブ形式の詳細解析はまだサポートされていません
- ko: 참고: 이 아카이브 형식의 상세 파싱은 아직 지원되지 않습니다

## file_archive_requires_lib
- en: Archive parsing - requires corresponding library
- zh: 压缩文件解析 - 需要相应库
- ja: アーカイブ解析 - 対応するライブラリが必要です
- ko: 아카이브 파싱 - 해당 라이브러리가 필요합니다

## file_archive_install_note
- en: Note: Install the corresponding archive library to enable parsing
- zh: 注意: 安装相应的压缩库以启用解析功能
- ja: 注意: 対応するアーカイブライブラリをインストールして解析機能を有効にしてください
- ko: 참고: 해당 아카이브 라이브러리를 설치하여 파싱 기능을 활성화하세요

## file_archive_parse_failed
- en: Archive parsing failed
- zh: 压缩文件解析失败
- ja: アーカイブ解析に失敗しました
- ko: 아카이브 파싱 실패

## file_pdf_analysis
- en: PDF Document Analysis
- zh: PDF 文档分析
- ja: PDF文書分析
- ko: PDF 문서 분석

## file_pdf_page_count
- en: Page count
- zh: 页数
- ja: ページ数
- ko: 페이지 수

## file_pdf_metadata
- en: Metadata
- zh: 元数据
- ja: メタデータ
- ko: 메타데이터

## file_pdf_text_preview
- en: Text content preview
- zh: 文本内容预览
- ja: テキスト内容プレビュー
- ko: 텍스트 내용 미리보기

## file_pdf_page_n
- en: Page {n}
- zh: 第 {n} 页
- ja: {n}ページ目
- ko: {n}페이지

## file_pdf_content_truncated
- en: ... (content truncated)
- zh: ... (内容已截断)
- ja: ... (内容が切り詰められました)
- ko: ... (내용 잘림)

## file_pdf_page_limit_note
- en: Note: Only showing first 3 pages out of {total} total pages
- zh: 注意: 仅显示前3页，共 {total} 页
- ja: 注意: 最初の3ページのみ表示しています（合計 {total} ページ）
- ko: 참고: 처음 3페이지만 표시합니다 (총 {total}페이지)

## file_pdf_requires_lib
- en: PDF file - requires PyPDF2 library
- zh: PDF 文件 - 需要 PyPDF2 库
- ja: PDFファイル - PyPDF2ライブラリが必要です
- ko: PDF 파일 - PyPDF2 라이브러리가 필요합니다

## file_pdf_install_note
- en: Note: Install PyPDF2 library to enable PDF parsing
- zh: 注意: 安装 PyPDF2 库以启用 PDF 解析功能
- ja: 注意: PyPDF2ライブラリをインストールしてPDF解析機能を有効にしてください
- ko: 참고: PyPDF2 라이브러리를 설치하여 PDF 파싱 기능을 활성화하세요

## file_pdf_parse_failed
- en: PDF parsing failed
- zh: PDF 解析失败
- ja: PDF解析に失敗しました
- ko: PDF 파싱 실패

## file_docx_analysis
- en: Word Document Analysis
- zh: Word 文档分析
- ja: Word文書分析
- ko: Word 문서 분석

## file_docx_paragraph_count
- en: Paragraph count
- zh: 段落数
- ja: 段落数
- ko: 단락 수

## file_docx_content_preview
- en: Content preview
- zh: 内容预览
- ja: 内容プレビュー
- ko: 내용 미리보기

## file_docx_paragraph_limit_note
- en: Note: Only showing first 50 paragraphs out of {total} total paragraphs
- zh: 注意: 仅显示前50段，共 {total} 段
- ja: 注意: 最初の50段落のみ表示しています（合計 {total} 段落）
- ko: 참고: 처음 50단락만 표시합니다 (총 {total}단락)

## file_docx_requires_lib
- en: Word document - requires python-docx library
- zh: Word 文档 - 需要 python-docx 库
- ja: Word文書 - python-docxライブラリが必要です
- ko: Word 문서 - python-docx 라이브러리가 필요합니다

## file_docx_install_note
- en: Note: Install python-docx library to enable Word parsing
- zh: 注意: 安装 python-docx 库以启用 Word 解析功能
- ja: 注意: python-docxライブラリをインストールしてWord解析機能を有効にしてください
- ko: 참고: python-docx 라이브러리를 설치하여 Word 파싱 기능을 활성화하세요

## file_docx_parse_failed
- en: Word parsing failed
- zh: Word 解析失败
- ja: Word解析に失敗しました
- ko: Word 파싱 실패

## file_image_ocr_analysis
- en: Image OCR Analysis
- zh: 图片 OCR 分析
- ja: 画像OCR分析
- ko: 이미지 OCR 분석

## file_image_dimensions
- en: Dimensions
- zh: 尺寸
- ja: サイズ
- ko: 크기

## file_image_mode
- en: Mode
- zh: 模式
- ja: モード
- ko: 모드

## file_image_extracted_text
- en: Extracted text
- zh: 提取的文字
- ja: 抽出されたテキスト
- ko: 추출된 텍스트

## file_image_no_text
- en: No text content detected
- zh: 未检测到文字内容
- ja: テキスト内容が検出されませんでした
- ko: 텍스트 내용이 감지되지 않음

## file_image_ocr_failed
- en: OCR extraction failed: {error}
- zh: OCR 提取失败: {error}
- ja: OCR抽出に失敗しました: {error}
- ko: OCR 추출 실패: {error}

## file_image_requires_lib
- en: Image OCR - requires pytesseract and Pillow libraries
- zh: 图片 OCR - 需要 pytesseract 和 Pillow 库
- ja: 画像OCR - pytesseractとPillowライブラリが必要です
- ko: 이미지 OCR - pytesseract 및 Pillow 라이브러리가 필요합니다

## file_image_install_note
- en: Note: Install pytesseract and Pillow libraries to enable OCR
- zh: 注意: 安装 pytesseract 和 Pillow 库以启用 OCR 功能
- ja: 注意: pytesseractとPillowライブラリをインストールしてOCR機能を有効にしてください
- ko: 참고: pytesseract 및 Pillow 라이브러리를 설치하여 OCR 기능을 활성화하세요

## file_image_parse_failed
- en: Image OCR failed
- zh: 图片 OCR 失败
- ja: 画像OCRに失敗しました
- ko: 이미지 OCR 실패

## file_large_metadata_only
- en: Large file - metadata only
- zh: 大文件 - 仅元数据
- ja: 大きなファイル - メタデータのみ
- ko: 큰 파일 - 메타데이터만

## file_large_note
- en: Note: File is too large, only metadata is provided. Use analyze_file_structure tool to analyze content.
- zh: 注意: 文件过大，仅提供元数据。如需分析内容，请使用 analyze_file_structure 工具。
- ja: 注意: ファイルが大きすぎるため、メタデータのみ提供されます。内容を分析するには、analyze_file_structureツールを使用してください。
- ko: 참고: 파일이 너무 커서 메타데이터만 제공됩니다. 내용을 분석하려면 analyze_file_structure 도구를 사용하세요.

## file_sampling_analysis
- en: File sampling - Size: {size} MB, Total lines: {lines}
- zh: 文件采样 - 大小: {size} MB, 总行数: {lines}
- ja: ファイルサンプリング - サイズ: {size} MB, 総行数: {lines}
- ko: 파일 샘플링 - 크기: {size} MB, 총 줄 수: {lines}

## file_sampling_header
- en: Header - first {n} lines
- zh: 头部 - 前 {n} 行
- ja: ヘッダー - 最初の {n} 行
- ko: 헤더 - 처음 {n}줄

## file_sampling_middle
- en: Middle sample - lines {start} - {end}
- zh: 中间采样 - 第 {start} - {end} 行
- ja: 中間サンプル - {start} - {end} 行目
- ko: 중간 샘플 - {start} - {end}줄

## file_sampling_tail
- en: Tail - last {n} lines
- zh: 尾部 - 后 {n} 行
- ja: 末尾 - 最後の {n} 行
- ko: 꼬리 - 마지막 {n}줄

## file_sampling_note
- en: Note: File has been sampled. Full content contains {lines} lines.
- zh: 注意: 文件已采样。完整内容包含 {lines} 行。
- ja: 注意: ファイルがサンプリングされました。完全な内容は {lines} 行を含みます。
- ko: 참고: 파일이 샘플링되었습니다. 전체 내용은 {lines}줄을 포함합니다.

## file_structure_analysis
- en: Large file structure analysis - Size: {size} MB, Total lines: {lines}
- zh: 大文件结构分析 - 大小: {size} MB, 总行数: {lines}
- ja: 大きなファイル構造分析 - サイズ: {size} MB, 総行数: {lines}
- ko: 큰 파일 구조 분석 - 크기: {size} MB, 총 줄 수: {lines}

## file_structure_detected_type
- en: Detected type
- zh: 检测类型
- ja: 検出されたタイプ
- ko: 감지된 유형

## file_structure_header_preview
- en: Header preview - first {n} lines
- zh: 头部预览 - 前 {n} 行
- ja: ヘッダープレビュー - 最初の {n} 行
- ko: 헤더 미리보기 - 처음 {n}줄

## file_structure_tail_preview
- en: Tail preview - last {n} lines
- zh: 尾部预览 - 后 {n} 行
- ja: 末尾プレビュー - 最後の {n} 行
- ko: 꼬리 미리보기 - 마지막 {n}줄

## file_structure_note
- en: Note: File is too large, only structure analysis and preview are provided.
- zh: 注意: 文件过大，仅提供结构分析和预览。
- ja: 注意: ファイルが大きすぎるため、構造分析とプレビューのみ提供されます。
- ko: 참고: 파일이 너무 커서 구조 분석과 미리보기만 제공됩니다.

## file_structure_suggestion
- en: Suggestion: Use analyze_file_structure tool to get detailed structure, or use read_file tool to read in chunks.
- zh: 建议: 使用 analyze_file_structure 工具获取详细结构，或使用 read_file 工具分块读取。
- ja: 提案: analyze_file_structureツールを使用して詳細な構造を取得するか、read_fileツールを使用してチャンクで読み取ります。
- ko: 제안: analyze_file_structure 도구를 사용하여 상세 구조를 가져오거나 read_file 도구를 사용하여 청크로 읽습니다.

## file_huge_metadata_only
- en: Huge file - metadata only
- zh: 超大文件 - 仅元数据
- ja: 巨大なファイル - メタデータのみ
- ko: 거대한 파일 - 메타데이터만

## file_huge_note
- en: Note: File is too large (> 100MB), cannot be parsed directly.
- zh: 注意: 文件过大（> 100MB），无法直接解析。
- ja: 注意: ファイルが大きすぎます（> 100MB）、直接解析できません。
- ko: 참고: 파일이 너무 큽니다 (> 100MB), 직접 파싱할 수 없습니다.

## file_huge_suggestions
- en: Suggested actions:
- zh: 建议操作:
- ja: 推奨アクション:
- ko: 권장 작업:

## file_huge_suggestion_1
- en: 1. Use analyze_file_structure tool to analyze file structure
- zh: 1. 使用 analyze_file_structure 工具分析文件结构
- ja: 1. analyze_file_structureツールを使用してファイル構造を分析
- ko: 1. analyze_file_structure 도구를 사용하여 파일 구조 분석

## file_huge_suggestion_2
- en: 2. Use read_file tool to read specific parts in chunks
- zh: 2. 使用 read_file 工具分块读取特定部分
- ja: 2. read_fileツールを使用して特定の部分をチャンクで読み取る
- ko: 2. read_file 도구를 사용하여 특정 부분을 청크로 읽기

## file_huge_suggestion_3
- en: 3. Or provide a smaller file for analysis
- zh: 3. 或提供更小的文件进行分析
- ja: 3. または分析用に小さなファイルを提供
- ko: 3. 또는 분석을 위해 더 작은 파일 제공

## file_email_headers
- en: Email headers
- zh: 邮件头
- ja: メールヘッダー
- ko: 이메일 헤더

# Vendor Auth Types

Human-readable names for integration auth method codes stored in local `provider_info.yaml` and `user_vendor_connections.auth_type`. Codes are stable English identifiers; use `get_vendor_auth_type_label` in `app/parsers/labels.py` for API responses.

## basic
- en: Username and password
- zh: 用户名和密码
- ja: ユーザー名とパスワード
- ko: 사용자 이름과 비밀번호

## api_key
- en: API key
- zh: API 密钥
- ja: APIキー
- ko: API 키

## oauth2
- en: OAuth 2.0
- zh: OAuth 2.0 授权
- ja: OAuth 2.0
- ko: OAuth 2.0

## access_key_secret
- en: Access key and secret
- zh: 访问密钥与私密密钥
- ja: アクセスキーとシークレットキー
- ko: 액세스 키 및 시크릿 키

## bearer
- en: Bearer token
- zh: Bearer 令牌
- ja: ベアラートークン
- ko: Bearer 토큰

## splunk_session_key
- en: Splunk session key
- zh: Splunk 会话密钥
- ja: Splunkセッションキー
- ko: Splunk 세션 키
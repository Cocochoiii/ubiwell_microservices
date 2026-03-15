.PHONY: up down logs ps test-smoke proto-gen replay-dlq chaos-test k8s-apply demo-up seed-demo bench-report load-dashboard e2e-flow capture-screenshots interview-report slo-report interview-demo test-backend test-backend-coverage test-frontend-jest quality-report quality-evidence security-deps security-secrets security-containers security-sbom security-sign-checklist security-verify-checklist security-compliance release-gate release-gate-strict industry-readiness board-readiness-summary board-ready bench-pipeline-throughput bench-data-loss collect-500h bench-ios-edge-reliability bench-edge-ml ios-edge-report edge-ml-report ios-edge-ml ios-edge-ml-advanced

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

ps:
	docker compose ps

test-smoke:
	k6 run k6/smoke.js

proto-gen:
	./.venv_codegen/bin/python -m grpc_tools.protoc -I ./shared/proto --python_out=./shared/gen --grpc_python_out=./shared/gen ./shared/proto/study_workflow.proto

replay-dlq:
	python3 scripts/replay_dlq.py

chaos-test:
	./scripts/chaos_test.sh participant-service 20

k8s-apply:
	kubectl apply -f k8s/namespace.yaml
	kubectl apply -f k8s/configmap.yaml
	kubectl apply -f k8s/secret.yaml
	kubectl apply -f k8s/stateful-infra.yaml
	kubectl apply -f k8s/services-apps.yaml
	kubectl apply -f k8s/deployments-apps.yaml

seed-demo:
	python3 scripts/seed_demo_data.py

demo-up:
	./scripts/demo_up.sh

bench-report:
	python3 benchmarks/report_benchmark.py

load-dashboard:
	./scripts/run_dashboard_load.sh

e2e-flow:
	cd tools/interview-demo && npm install && npm run e2e

capture-screenshots:
	cd tools/interview-demo && npm install && npx playwright install chromium && npm run capture

interview-report:
	python3 scripts/generate_interview_report.py

slo-report:
	python3 scripts/generate_slo_report.py

test-backend:
	python3 -m venv .venv_test
	./.venv_test/bin/pip install -q pytest pytest-asyncio
	./.venv_test/bin/pip install -q -r services/api-gateway/requirements.txt -r services/realtime-service/requirements.txt -r services/report-service/requirements.txt -r services/collector-service/requirements.txt
	./.venv_test/bin/pytest -q tests

test-backend-coverage:
	python3 -m venv .venv_test
	./.venv_test/bin/pip install -q pytest pytest-asyncio pytest-cov
	./.venv_test/bin/pip install -q -r services/api-gateway/requirements.txt -r services/realtime-service/requirements.txt -r services/report-service/requirements.txt -r services/collector-service/requirements.txt
	./.venv_test/bin/pytest -q tests \
		--junitxml=docs/perf/results/pytest-results.xml \
		--cov=shared/utils \
		--cov-report=xml:docs/perf/results/pytest-coverage.xml \
		--cov-fail-under=92

test-frontend-jest:
	cd apps/web-dashboard && npm install && npm run test:coverage

quality-report:
	python3 scripts/generate_quality_engineering_report.py

quality-evidence: test-backend-coverage test-frontend-jest quality-report

security-deps:
	python3 -m venv .venv_security
	./.venv_security/bin/pip install -q pip-audit
	PATH="./.venv_security/bin:$$PATH" python3 scripts/dependency_vuln_scan.py

security-secrets:
	python3 scripts/secret_scan.py

security-containers:
	python3 scripts/container_scan.py

security-sbom:
	python3 scripts/generate_sbom.py

security-sign-checklist:
	python3 scripts/sign_release_checklist.py --signer "$${RELEASE_SIGNER:-local-dev}"

security-verify-checklist:
	python3 scripts/sign_release_checklist.py --verify

security-compliance: security-deps security-secrets security-containers security-sbom security-sign-checklist

release-gate:
	python3 scripts/release_gate.py

release-gate-strict:
	python3 scripts/release_gate.py --strict

industry-readiness: quality-evidence slo-report ios-edge-report security-compliance release-gate

board-readiness-summary:
	python3 scripts/generate_board_readiness_summary.py

board-ready: quality-evidence security-compliance bench-pipeline-throughput bench-data-loss slo-report ios-edge-report release-gate-strict board-readiness-summary

interview-demo: bench-report load-dashboard capture-screenshots interview-report slo-report

collect-500h:
	curl -X POST "http://localhost:8007/pipeline/collect/simulate-500h?tenant_id=tenant-a&study_id=study-a&source_name=wearable-sim"

bench-pipeline-throughput:
	docker run --rm --network ubiwell_microservices_default \
		-v "$$(pwd):/work" -w /work \
		-e KAFKA_BOOTSTRAP_SERVERS=redpanda:9092 \
		python:3.11-slim sh -lc "pip install -q kafka-python lz4 && python benchmarks/pipeline_throughput.py"

bench-data-loss:
	python3 -m venv .venv_bench
	./.venv_bench/bin/pip install -q --upgrade pip
	./.venv_bench/bin/python benchmarks/data_loss_reduction.py

bench-ios-edge-reliability:
	python3 benchmarks/ios_edge_reliability.py

bench-edge-ml:
	python3 -m venv .venv_edge_ml_adv
	./.venv_edge_ml_adv/bin/pip install -q numpy scikit-learn
	./.venv_edge_ml_adv/bin/python benchmarks/edge_ml_runtime.py

ios-edge-report:
	python3 scripts/generate_ios_edge_report.py

edge-ml-report:
	python3 scripts/generate_edge_ml_report.py

ios-edge-ml:
	python3 -m venv .venv_edge_ml
	./.venv_edge_ml/bin/pip install -q -r ml/edge-models/requirements.txt
	./.venv_edge_ml/bin/python ml/edge-models/train_export_tflite.py

ios-edge-ml-advanced:
	python3 -m venv .venv_edge_ml_adv
	./.venv_edge_ml_adv/bin/pip install -q numpy scikit-learn
	./.venv_edge_ml_adv/bin/python ml/edge-models/train_advanced_edge_model.py

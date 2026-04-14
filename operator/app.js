const DEFAULTS = {
    repo: "victorres11/pbp-analysis",
    workflowFile: "brief-live-refresh.yml",
    team1: "Washington",
    team2: "Ohio State",
    season: "2025",
    lastN: "3",
    briefFormat: "both",
    runTests: false,
    strictVerification: true,
    includeEnrichment: true,
};

const STORAGE_KEYS = {
    dispatch: "brief-operator-dispatch",
};

const SUPPORTED_TEAM_GROUPS = [
    {
        label: "Big Ten",
        teams: [
            "Illinois",
            "Indiana",
            "Iowa",
            "Maryland",
            "Michigan",
            "Michigan State",
            "Minnesota",
            "Nebraska",
            "Northwestern",
            "Ohio State",
            "Oregon",
            "Penn State",
            "Purdue",
            "Rutgers",
            "UCLA",
            "USC",
            "Washington",
            "Wisconsin",
        ],
    },
    {
        label: "Independent",
        teams: ["Notre Dame"],
    },
    {
        label: "Big 12",
        teams: ["Utah"],
    },
];

const WORKFLOW_PAGE = (repo) => `https://github.com/${repo}/actions/workflows/${DEFAULTS.workflowFile}`;
const RELEASES_PAGE = (repo) => `https://github.com/${repo}/releases`;
const RUNBOOK_PAGE = (repo) => `https://github.com/${repo}/blob/main/docs/demo-runbook.md`;
const CONTRACT_PAGE = (repo) => `https://github.com/${repo}/blob/main/docs/published-artifact-contract.md`;
const LAUNCH_POLICY_PAGE = (repo) => `https://github.com/${repo}/blob/main/docs/operator-launch-policy.md`;
const WARNING_REVIEW_PAGE = (repo) => `https://github.com/${repo}/blob/main/docs/operator-warning-review.md`;
const ENRICHMENT_CONTRACT_PAGE = (repo) => `https://github.com/${repo}/blob/main/docs/enrichment-artifact-contract.md`;
const ALERTS_PAGE = (repo) =>
    `https://github.com/${repo}/issues?q=is%3Aissue%20state%3Aopen%20%22Brief%20Live%20Refresh%20Alerts%22`;

const elements = {};
let loading = false;
let dispatchRefreshTimer = null;
let dispatchRefreshRemaining = 0;

document.addEventListener("DOMContentLoaded", () => {
    cacheElements();
    populateTeamOptions();
    hydrateSettings();
    bindEvents();
    refreshDashboard();
});

function cacheElements() {
    for (const id of [
        "team1Input",
        "team2Input",
        "seasonInput",
        "lastNInput",
        "runTestsInput",
        "strictVerificationInput",
        "includeEnrichmentInput",
        "refreshButton",
        "dispatchButton",
        "settingsMessage",
        "dispatchMessage",
        "statusStrip",
        "runsPanel",
        "latestRunReviewPanel",
        "warningReviewPanel",
        "reviewMessage",
        "workflowLink",
        "dispatchForm",
    ]) {
        elements[id] = document.getElementById(id);
    }
}

function populateTeamOptions() {
    const optionMarkup = SUPPORTED_TEAM_GROUPS.map((group) => {
        const options = group.teams
            .map((team) => `<option value="${escapeAttribute(team)}">${escapeHtml(team)}</option>`)
            .join("");
        return `<optgroup label="${escapeAttribute(group.label)}">${options}</optgroup>`;
    }).join("");

    elements.team1Input.innerHTML = optionMarkup;
    elements.team2Input.innerHTML = optionMarkup;
    elements.team1Input.value = DEFAULTS.team1;
    elements.team2Input.value = DEFAULTS.team2;
}

function setSelectValue(select, value, fallback) {
    select.value = value;
    if (!select.value) {
        select.value = fallback;
    }
}

function hydrateSettings() {
    const savedDispatch = loadJsonStorage(STORAGE_KEYS.dispatch);

    if (savedDispatch) {
        setSelectValue(elements.team1Input, savedDispatch.team1 || DEFAULTS.team1, DEFAULTS.team1);
        setSelectValue(elements.team2Input, savedDispatch.team2 || DEFAULTS.team2, DEFAULTS.team2);
        elements.seasonInput.value = savedDispatch.season || DEFAULTS.season;
        elements.lastNInput.value = savedDispatch.lastN || DEFAULTS.lastN;
        elements.runTestsInput.checked = Boolean(savedDispatch.runTests);
        elements.strictVerificationInput.checked = savedDispatch.strictVerification !== false;
        elements.includeEnrichmentInput.checked = savedDispatch.includeEnrichment !== false;
    } else {
        setSelectValue(elements.team1Input, DEFAULTS.team1, DEFAULTS.team1);
        setSelectValue(elements.team2Input, DEFAULTS.team2, DEFAULTS.team2);
    }
}

function bindEvents() {
    elements.refreshButton.addEventListener("click", () => refreshDashboard());
    elements.dispatchForm.addEventListener("submit", handleDispatch);
    document.addEventListener("click", handleDocumentClick);

    elements.seasonInput.addEventListener("change", handleDispatchSettingsChanged);

    for (const field of [
        elements.team1Input,
        elements.team2Input,
        elements.lastNInput,
        elements.runTestsInput,
        elements.strictVerificationInput,
        elements.includeEnrichmentInput,
    ]) {
        field.addEventListener("change", persistDispatchSettings);
    }
}

async function handleDocumentClick(event) {
    const button = event.target.closest(".artifact-download-button");
    if (!button) {
        return;
    }
    event.preventDefault();
    const downloadUrl = button.dataset.artifactUrl || "";
    const filename = button.dataset.artifactName || "artifact.zip";
    if (!downloadUrl) {
        setInlineMessage(elements.reviewMessage, "Artifact download URL is missing for this run output.", "warning");
        return;
    }
    await downloadArtifactArchive(button, downloadUrl, filename);
}

function handleDispatchSettingsChanged() {
    persistDispatchSettings();
}

function persistDispatchSettings() {
    localStorage.setItem(
        STORAGE_KEYS.dispatch,
        JSON.stringify({
            team1: elements.team1Input.value.trim() || DEFAULTS.team1,
            team2: elements.team2Input.value.trim() || DEFAULTS.team2,
            season: elements.seasonInput.value.trim() || DEFAULTS.season,
            lastN: elements.lastNInput.value.trim() || DEFAULTS.lastN,
            runTests: elements.runTestsInput.checked,
            strictVerification: elements.strictVerificationInput.checked,
            includeEnrichment: elements.includeEnrichmentInput.checked,
        }),
    );
}

function normalizedDispatchInputs() {
    return {
        team1: elements.team1Input.value.trim() || DEFAULTS.team1,
        team2: elements.team2Input.value.trim() || DEFAULTS.team2,
        season: elements.seasonInput.value.trim() || DEFAULTS.season,
        last_n: elements.lastNInput.value.trim() || DEFAULTS.lastN,
        brief_format: DEFAULTS.briefFormat,
        run_tests: String(elements.runTestsInput.checked),
        strict_verification: String(elements.strictVerificationInput.checked),
        include_enrichment: String(elements.includeEnrichmentInput.checked),
    };
}

function validateDispatchInputs(inputs) {
    if (!inputs.team1 || !inputs.team2) {
        return "Choose both teams before dispatching a run.";
    }
    if (inputs.team1 === inputs.team2) {
        return "Team 1 and Team 2 must be different.";
    }
    if (!/^\d{4}$/.test(inputs.season)) {
        return "Season must be a four-digit year.";
    }
    return "";
}

async function handleDispatch(event) {
    event.preventDefault();

    const repo = normalizedRepo();
    const inputs = normalizedDispatchInputs();
    const validationError = validateDispatchInputs(inputs);
    if (validationError) {
        setInlineMessage(elements.dispatchMessage, validationError, "warning");
        return;
    }
    persistDispatchSettings();

    elements.dispatchButton.disabled = true;
    setInlineMessage(
        elements.dispatchMessage,
        `Dispatching a new live refresh for ${inputs.team1} vs ${inputs.team2} (${inputs.season})…`,
        "warning",
    );

    try {
        await githubRequest(
            `/repos/${encodeRepo(repo)}/actions/workflows/${encodeURIComponent(DEFAULTS.workflowFile)}/dispatches`,
            {
                method: "POST",
                body: {
                    ref: "main",
                    inputs,
                },
            },
        );
        setInlineMessage(
            elements.dispatchMessage,
            `Dispatch accepted by GitHub. Refreshing run history automatically now.`,
            "success",
        );
        startDispatchRefreshLoop();
    } catch (error) {
        setInlineMessage(elements.dispatchMessage, formatError(error), "error");
    } finally {
        syncActionButtons();
    }
}

function startDispatchRefreshLoop() {
    if (dispatchRefreshTimer) {
        window.clearTimeout(dispatchRefreshTimer);
        dispatchRefreshTimer = null;
    }

    dispatchRefreshRemaining = 8;

    const tick = async () => {
        await refreshDashboard({ quiet: true });
        dispatchRefreshRemaining -= 1;

        if (dispatchRefreshRemaining <= 0) {
            dispatchRefreshTimer = null;
            return;
        }

        dispatchRefreshTimer = window.setTimeout(tick, 2500);
    };

    dispatchRefreshTimer = window.setTimeout(tick, 500);
}

async function refreshDashboard({ quiet = false } = {}) {
    const repo = normalizedRepo();
    const season = normalizedSeason();

    persistDispatchSettings();

    setInlineMessage(elements.reviewMessage, "");
    setLoadingState(true);

    const [runsResult, publishedResult] = await Promise.allSettled([
        fetchWorkflowRuns(repo),
        fetchPublishedSeason(repo, season),
    ]);
    const latestRun = runsResult.status === "fulfilled" ? runsResult.value.runs[0] : null;
    const latestRunArtifactsResult = latestRun
        ? await Promise.allSettled([fetchRunArtifacts(repo, latestRun.id)]).then((results) => results[0])
        : null;

    renderLatestRunBlock(runsResult, repo);
    renderStatusStrip(runsResult, publishedResult);
    renderReviewPanels(runsResult, publishedResult, latestRunArtifactsResult, repo, season);

    if (!quiet) {
        const resultSet = [runsResult, publishedResult];
        if (latestRunArtifactsResult) {
            resultSet.push(latestRunArtifactsResult);
        }
        const successCount = resultSet.filter((result) => result.status === "fulfilled").length;
        const message =
            successCount === resultSet.length
                ? "Dashboard refreshed through the Mac mini relay."
                : "Dashboard refreshed with partial data. Check the Mac mini relay or GitHub token if data is missing.";
        const tone = successCount === resultSet.length ? "success" : "warning";
        setInlineMessage(elements.settingsMessage, message, tone);
    }

    setLoadingState(false);
}

async function fetchWorkflowRuns(repo) {
    const payload = await githubRequest(
        `/repos/${encodeRepo(repo)}/actions/workflows/${encodeURIComponent(DEFAULTS.workflowFile)}/runs?per_page=8`,
    );
    return {
        workflowUrl: WORKFLOW_PAGE(repo),
        runs: Array.isArray(payload.workflow_runs) ? payload.workflow_runs : [],
    };
}

async function fetchPublishedSeason(repo, season) {
    const tag = `brief-artifacts-${season}`;
    const release = await githubRequest(`/repos/${encodeRepo(repo)}/releases/tags/${encodeURIComponent(tag)}`);
    const summaryFilename = `game_prep_pipeline_summary_${season}.json`;
    const summaryAsset = Array.isArray(release.assets)
        ? release.assets.find((asset) => asset && asset.name === summaryFilename)
        : null;

    let summary = null;
    if (summaryAsset && typeof summaryAsset.url === "string") {
        summary = await githubRequest(summaryAsset.url, {
            accept: "application/octet-stream",
        });
    }

    return {
        tag,
        release,
        summary,
        summaryAsset,
    };
}

async function fetchRunArtifacts(repo, runId) {
    const payload = await githubRequest(
        `/repos/${encodeRepo(repo)}/actions/runs/${encodeURIComponent(String(runId))}/artifacts?per_page=20`,
    );
    return Array.isArray(payload.artifacts) ? payload.artifacts : [];
}

function renderStatusStrip(runsResult, publishedResult) {
    const badges = [];

    if (runsResult.status === "fulfilled" && runsResult.value.runs.length) {
        const latestRun = runsResult.value.runs[0];
        badges.push(badgeHtml(`latest run: ${workflowLabel(latestRun)}`, workflowTone(latestRun)));
    } else {
        badges.push(badgeHtml("latest run unavailable", "warning"));
    }

    if (publishedResult.status === "fulfilled" && publishedResult.value.summary) {
        const summary = publishedResult.value.summary;
        const warningCount = Array.isArray(summary.warnings) ? summary.warnings.length : 0;
        badges.push(
            badgeHtml(
                `published: ${summary.artifact_contract?.publishable ? "publishable" : "non-publishable"}`,
                summary.artifact_contract?.publishable ? "success" : "warning",
            ),
        );
        badges.push(badgeHtml(`${warningCount} warning${warningCount === 1 ? "" : "s"}`, warningCount ? "warning" : "success"));
    } else {
        badges.push(badgeHtml("published summary unavailable", "warning"));
    }

    elements.statusStrip.innerHTML = badges.join("");
}

async function githubRequest(pathOrUrl, { method = "GET", accept = "application/vnd.github+json", body } = {}) {
    const response = await fetch("/api/operator/github", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            pathOrUrl,
            method,
            accept,
            body,
        }),
    });

    if (response.status === 204) {
        return null;
    }

    if (!response.ok) {
        const message = await extractProxyErrorMessage(response);
        throw new Error(message);
    }

    const text = await response.text();
    if (!text) {
        return null;
    }
    try {
        return JSON.parse(text);
    } catch (_jsonError) {
        return text;
    }
}

async function extractProxyErrorMessage(response) {
    const fallback = `Operator relay request failed (${response.status} ${response.statusText})`;
    try {
        const text = await response.text();
        if (!text) {
            return fallback;
        }
        if (looksLikeStaticServerRelayFailure(response, text)) {
            return `Operator relay unavailable. Open this dashboard through ./operator/start-operator.sh or python3 operator/server.py, not python3 -m http.server. (${response.status})`;
        }
        try {
            const payload = JSON.parse(text);
            if (typeof payload.message === "string") {
                return `${payload.message} (${response.status})`;
            }
        } catch (_jsonError) {
            return `${text.trim()} (${response.status})`;
        }
    } catch (_readError) {
        return fallback;
    }
    return fallback;
}

function looksLikeStaticServerRelayFailure(response, text) {
    const contentType = (response.headers.get("content-type") || "").toLowerCase();
    if (!contentType.includes("text/html")) {
        return false;
    }
    const normalized = text.toLowerCase();
    return (
        normalized.includes("unsupported method ('post')") ||
        normalized.includes("httpstatus.not_implemented") ||
        normalized.includes("<title>error response</title>") ||
        normalized.includes("<h1>error response</h1>")
    );
}

async function downloadArtifactArchive(button, downloadUrl, filename) {
    button.disabled = true;
    setInlineMessage(elements.reviewMessage, `Downloading ${filename}…`, "warning");

    try {
        const response = await fetch(downloadProxyUrl(downloadUrl, filename));
        if (!response.ok) {
            throw new Error(await extractProxyErrorMessage(response));
        }

        const blob = await response.blob();
        const objectUrl = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = objectUrl;
        anchor.download = filename;
        document.body.append(anchor);
        anchor.click();
        anchor.remove();
        window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
        setInlineMessage(elements.reviewMessage, `Downloaded ${filename}.`, "success");
    } catch (error) {
        setInlineMessage(elements.reviewMessage, formatError(error), "error");
    } finally {
        button.disabled = false;
    }
}

function renderLatestRunBlock(result, repo) {
    elements.workflowLink.href = WORKFLOW_PAGE(repo);

    if (result.status === "rejected") {
        elements.runsPanel.innerHTML = renderErrorBlock(
            `Could not load workflow runs. ${escapeHtml(formatError(result.reason))}`,
        );
        return;
    }

    const runs = result.value.runs;
    if (!runs.length) {
        elements.runsPanel.innerHTML = renderEmptyState("No workflow runs are visible for this workflow yet.");
        return;
    }

    const rows = runs
        .map((run) => {
            const tone = workflowTone(run);
            return `
                <tr>
                    <td>
                        <a class="text-link mono" href="${escapeAttribute(run.html_url)}" target="_blank" rel="noreferrer">
                            #${escapeHtml(String(run.run_number || "—"))}
                        </a>
                    </td>
                    <td>${badgeHtml(workflowLabel(run), tone)}</td>
                    <td>${escapeHtml(run.event || "unknown")}</td>
                    <td>${escapeHtml(run.display_title || "Brief Live Refresh")}</td>
                    <td>${escapeHtml(run.actor?.login || "unknown")}</td>
                    <td class="mono">${escapeHtml(run.head_branch || "main")}</td>
                    <td>${escapeHtml(formatDateTime(run.updated_at))}<div class="muted">${escapeHtml(relativeTime(run.updated_at))}</div></td>
                </tr>
            `;
        })
        .join("");

    elements.runsPanel.innerHTML = `
        <table>
            <thead>
                <tr>
                    <th>Run</th>
                    <th>Status</th>
                    <th>Trigger</th>
                    <th>Title</th>
                    <th>Actor</th>
                    <th>Branch</th>
                    <th>Updated</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
    `;
}

function renderReviewPanels(runsResult, publishedResult, latestRunArtifactsResult, repo, season) {
    renderLatestRunReviewPanel(runsResult, latestRunArtifactsResult);
    renderWarningReviewPanel(runsResult, publishedResult, repo, season);
}

function renderLatestRunReviewPanel(runsResult, latestRunArtifactsResult) {
    if (runsResult.status === "rejected") {
        elements.latestRunReviewPanel.innerHTML = renderErrorBlock(
            `Could not load the latest run. ${escapeHtml(formatError(runsResult.reason))}`,
        );
        return;
    }

    const latestRun = runsResult.value.runs[0];
    if (!latestRun) {
        elements.latestRunReviewPanel.innerHTML = renderEmptyState("Run evidence will appear after the first workflow execution.");
        return;
    }

    const artifacts = latestRunArtifactsResult?.status === "fulfilled" ? latestRunArtifactsResult.value : [];
    const artifactError = latestRunArtifactsResult?.status === "rejected"
        ? formatError(latestRunArtifactsResult.reason)
        : "";
    const investigationArtifacts = prioritizedArtifacts(artifacts);
    const briefArtifact = investigationArtifacts.find((artifact) => artifact.name === "brief-live-refresh-smoke-brief") || null;
    const supportingArtifacts = investigationArtifacts.filter((artifact) => artifact.name !== "brief-live-refresh-smoke-brief");

    elements.latestRunReviewPanel.innerHTML = `
        <div class="message-block">
            <div class="button-row">
                ${badgeHtml(workflowLabel(latestRun), workflowTone(latestRun))}
                ${badgeHtml(latestRun.event || "unknown", "info")}
                ${badgeHtml(relativeTime(latestRun.updated_at), workflowTone(latestRun))}
            </div>
            <div class="kv">
                ${kvRow("Run", `<a class="text-link mono" href="${escapeAttribute(latestRun.html_url)}" target="_blank" rel="noreferrer">#${escapeHtml(String(latestRun.run_number || "—"))}</a>`)}
                ${kvRow("Updated", `${formatDateTime(latestRun.updated_at)} (${relativeTime(latestRun.updated_at)})`)}
                ${kvRow("Actor", latestRun.actor?.login || "unknown")}
                ${kvRow("Branch", latestRun.head_branch || "main")}
            </div>
            <div class="asset-actions">
                <a class="button secondary" href="${escapeAttribute(latestRun.html_url)}" target="_blank" rel="noreferrer">Open workflow run</a>
                <a class="button ghost" href="${escapeAttribute(latestRun.html_url)}#artifacts" target="_blank" rel="noreferrer">Open run artifacts</a>
            </div>
        </div>
        ${
            briefArtifact
                ? `
                    <div class="message-block success">
                        <div class="artifact-review-head">
                            <h3>Client brief bundle</h3>
                            ${badgeHtml(Boolean(briefArtifact.expired) ? "expired" : "ready", Boolean(briefArtifact.expired) ? "warning" : "success")}
                        </div>
                        <p>${escapeHtml(
                            Boolean(briefArtifact.expired)
                                ? "The latest brief artifact has expired in GitHub. Open the run artifacts page if you need retention details."
                                : "This is the attachment bundle from the latest run. Manual launches now default to both HTML and Markdown; older runs may still contain only one format.",
                        )}</p>
                        <div class="kv compact">
                            ${kvRow("Updated", formatDateTime(briefArtifact.updated_at))}
                            ${kvRow("Size", formatBytes(briefArtifact.size_in_bytes))}
                            ${kvRow("Artifact", `<span class="mono">${escapeHtml(briefArtifact.name || "brief-live-refresh-smoke-brief")}</span>`)}
                        </div>
                        <div class="asset-actions">
                            <button
                                class="button primary artifact-download-button"
                                type="button"
                                data-artifact-url="${escapeAttribute(briefArtifact.archive_download_url || "")}"
                                data-artifact-name="${escapeAttribute(briefArtifact.name || "brief")}.zip"
                                ${briefArtifact.expired ? "disabled" : ""}
                            >Download brief zip</button>
                            <a class="button ghost" href="${escapeAttribute(latestRun.html_url)}#artifacts" target="_blank" rel="noreferrer">Open run artifacts</a>
                        </div>
                    </div>
                `
                : ""
        }
        ${
            supportingArtifacts.length
                ? `
                    <div class="message-block">
                        <h3>Supporting artifacts</h3>
                        <div class="artifact-list">
                            ${supportingArtifacts.map((artifact) => renderArtifactReviewCard(artifact)).join("")}
                        </div>
                    </div>
                `
                : !briefArtifact
                    ? renderEmptyState(
                    artifactError
                        ? `Could not load run artifacts. ${artifactError}`
                        : "No artifacts are visible yet for the latest run.",
                )
                    : ""
        }
        <div class="message-block">
            <h3>Operator review path</h3>
            <ul class="list">
                <li>Start with the status view artifact for publication posture and warning counts.</li>
                <li>Use the pipeline summary artifact when you need exact non-publishable reasons and raw warning strings.</li>
                <li>Use the client brief bundle to inspect and download the actual client-facing attachment candidate.</li>
            </ul>
        </div>
    `;
}

function renderWarningReviewPanel(runsResult, publishedResult, repo, season) {
    if (publishedResult.status === "rejected") {
        elements.warningReviewPanel.innerHTML = renderErrorBlock(
            `Could not load warning posture. ${escapeHtml(formatError(publishedResult.reason))}`,
        );
        return;
    }

    const summary = publishedResult.value.summary;
    const release = publishedResult.value.release;
    if (!summary) {
        elements.warningReviewPanel.innerHTML = renderEmptyState(
            "Published warning review depends on the rolling release summary JSON.",
        );
        return;
    }

    const warnings = Array.isArray(summary.warnings) ? summary.warnings : [];
    const groupedWarnings = groupWarningsByCategory(warnings);
    const validation = summary.validation || {};
    const artifactContract = summary.artifact_contract || {};
    const nonPublishableReasons = Array.isArray(artifactContract.non_publishable_reasons)
        ? artifactContract.non_publishable_reasons
        : [];
    const latestRun = runsResult.status === "fulfilled" ? runsResult.value.runs[0] : null;
    const summaryAsset = publishedResult.value.summaryAsset;
    const verificationAsset = findReleaseAsset(release, "cfbstats_verification_");

    elements.warningReviewPanel.innerHTML = `
        <div class="message-block">
            <div class="button-row">
                ${badgeHtml(artifactContract.publishable ? "publishable" : "non-publishable", artifactContract.publishable ? "success" : "warning")}
                ${badgeHtml(`${validation.verification_warning_count ?? 0} verification warn`, Number(validation.verification_warning_count || 0) ? "warning" : "success")}
                ${badgeHtml(`${warnings.length} summary warning${warnings.length === 1 ? "" : "s"}`, warnings.length ? "warning" : "success")}
            </div>
            <div class="kv">
                ${kvRow("Generated", `${formatDateTime(summary.generated_at)} (${relativeTime(summary.generated_at)})`)}
                ${kvRow("Artifact set", `<span class="mono">${escapeHtml(artifactContract.artifact_set_id || "unknown")}</span>`)}
                ${kvRow("Verification fails", String(validation.verification_fail_count ?? "unknown"))}
                ${kvRow("Enrichment", summary.enrichment_contract?.artifact_status || "unknown")}
            </div>
            <div class="asset-actions">
                <a class="button secondary" href="${escapeAttribute(release.html_url || `https://github.com/${repo}/releases/tag/brief-artifacts-${season}`)}" target="_blank" rel="noreferrer">Open rolling release</a>
                ${
                    summaryAsset?.url
                        ? `<a class="button ghost" href="${escapeAttribute(downloadProxyUrl(summaryAsset.url, summaryAsset.name || "summary.json", "application/octet-stream"))}">Open summary JSON</a>`
                        : ""
                }
                ${
                    verificationAsset?.url
                        ? `<a class="button ghost" href="${escapeAttribute(downloadProxyUrl(verificationAsset.url, verificationAsset.name || "verification.json", "application/octet-stream"))}">Open verification report</a>`
                        : ""
                }
                ${
                    latestRun?.html_url
                        ? `<a class="button ghost" href="${escapeAttribute(latestRun.html_url)}" target="_blank" rel="noreferrer">Open latest workflow run</a>`
                        : ""
                }
                <a class="button ghost" href="${escapeAttribute(ALERTS_PAGE(repo))}" target="_blank" rel="noreferrer">Open alerts thread</a>
            </div>
        </div>
        ${
            warnings.length
                ? `
                    <div class="message-block warning">
                        <h3>Published warning groups</h3>
                        <div class="warning-groups">
                            ${groupedWarnings.map((group) => renderWarningGroup(group)).join("")}
                        </div>
                    </div>
                `
                : `
                    <div class="message-block success">
                        <h3>Published warning groups</h3>
                        <p>No summary warnings are recorded on the rolling release right now.</p>
                    </div>
                `
        }
        ${
            nonPublishableReasons.length
                ? `
                    <div class="message-block warning">
                        <h3>Non-publishable reasons</h3>
                        <div class="chip-list">
                            ${nonPublishableReasons.map((reason) => badgeHtml(reason, "warning")).join("")}
                        </div>
                    </div>
                `
                : ""
        }
        <div class="message-block">
            <h3>Review standard</h3>
            <ul class="list">
                <li>Warnings are visible by design. They are the review queue, not an implementation detail.</li>
                <li>Expected special cases can be accepted, but they should still be explainable from the summary, verification report, or smoke brief.</li>
                <li>If a warning cannot be explained from those artifacts, treat it as investigate-first before client delivery.</li>
            </ul>
        </div>
    `;
}

function prioritizedArtifacts(artifacts) {
    const order = new Map([
        ["brief-live-refresh-status-view", 0],
        ["brief-live-refresh-summary", 1],
        ["brief-live-refresh-smoke-brief", 2],
        ["brief-live-refresh-published-artifacts", 3],
        ["brief-live-refresh-scratch-artifacts", 4],
    ]);
    return [...artifacts].sort((left, right) => {
        const leftRank = order.has(left.name) ? order.get(left.name) : 99;
        const rightRank = order.has(right.name) ? order.get(right.name) : 99;
        return leftRank - rightRank;
    });
}

function renderArtifactReviewCard(artifact) {
    const expired = Boolean(artifact.expired);
    const tone = expired ? "warning" : "info";
    return `
        <article class="artifact-review-card">
            <div class="artifact-review-head">
                <h3>${escapeHtml(runArtifactLabel(artifact.name || "artifact"))}</h3>
                ${badgeHtml(expired ? "expired" : "available", tone)}
            </div>
            <p class="muted mono">${escapeHtml(artifact.name || "unknown-artifact")}</p>
            <div class="kv compact">
                ${kvRow("Updated", formatDateTime(artifact.updated_at))}
                ${kvRow("Size", formatBytes(artifact.size_in_bytes))}
            </div>
            <div class="asset-actions">
                <button
                    class="button secondary artifact-download-button"
                    type="button"
                    data-artifact-url="${escapeAttribute(artifact.archive_download_url || "")}"
                    data-artifact-name="${escapeAttribute(artifact.name || "artifact")}.zip"
                    ${expired ? "disabled" : ""}
                >${escapeHtml(artifactDownloadLabel(artifact.name || "artifact"))}</button>
            </div>
        </article>
    `;
}

function runArtifactLabel(name) {
    const labels = {
        "brief-live-refresh-status-view": "Status view",
        "brief-live-refresh-summary": "Pipeline summary",
        "brief-live-refresh-smoke-brief": "Client brief bundle",
        "brief-live-refresh-published-artifacts": "Published artifact set",
        "brief-live-refresh-scratch-artifacts": "Scratch artifact set",
    };
    return labels[name] || name;
}

function artifactDownloadLabel(name) {
    if (name === "brief-live-refresh-smoke-brief") {
        return "Download brief zip";
    }
    return "Download in dashboard";
}

function findReleaseAsset(release, prefix) {
    const assets = Array.isArray(release?.assets) ? release.assets : [];
    return assets.find((asset) => typeof asset?.name === "string" && asset.name.startsWith(prefix)) || null;
}

function classifyWarning(warning) {
    const text = String(warning || "").toLowerCase();
    if (text.includes("turnover")) {
        return { key: "turnovers", label: "Turnovers", tone: "warning" };
    }
    if (text.includes("parity") || text.includes("mismatch")) {
        return { key: "parity", label: "Parity", tone: "warning" };
    }
    if (text.includes("verification") || text.includes("cfbstats")) {
        return { key: "verification", label: "Verification", tone: "warning" };
    }
    if (text.includes("enrichment") || text.includes("pff") || text.includes("api")) {
        return { key: "enrichment", label: "Enrichment", tone: "info" };
    }
    if (text.includes("duration budget") || text.includes("[heartbeat]") || text.includes("interrupted")) {
        return { key: "runtime", label: "Runtime", tone: "info" };
    }
    if (text.includes("alias") || text.includes("offense token") || text.includes("play tree")) {
        return { key: "parser", label: "Parser", tone: "warning" };
    }
    return { key: "other", label: "Other", tone: "neutral" };
}

function groupWarningsByCategory(warnings) {
    const grouped = new Map();
    for (const warning of warnings) {
        const category = classifyWarning(warning);
        if (!grouped.has(category.key)) {
            grouped.set(category.key, {
                ...category,
                warnings: [],
            });
        }
        grouped.get(category.key).warnings.push(warning);
    }
    return [...grouped.values()];
}

function renderWarningGroup(group) {
    return `
        <section class="warning-group">
            <div class="warning-group-head">
                ${badgeHtml(group.label, group.tone)}
                <span class="muted">${escapeHtml(String(group.warnings.length))} item${group.warnings.length === 1 ? "" : "s"}</span>
            </div>
            <ul class="list warning-list">
                ${group.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}
            </ul>
        </section>
    `;
}

function renderPublishedBlock(result, repo, season) {
    const rollingUrl = `https://github.com/${repo}/releases/tag/brief-artifacts-${season}`;
    elements.rollingReleaseLink.href = rollingUrl;

    if (result.status === "rejected") {
        const message = `Could not load the rolling release for ${season}. ${escapeHtml(formatError(result.reason))}`;
        elements.publishedSummaryPanel.innerHTML = renderErrorBlock(message);
        elements.assetPanel.innerHTML = renderEmptyState("Published asset links will appear once the rolling release is readable.");
        return;
    }

    const { release, summary } = result.value;
    if (!summary) {
        elements.publishedSummaryPanel.innerHTML = renderEmptyState(
            "The rolling release exists, but the published summary JSON is missing.",
        );
    } else {
        const artifactSetId = summary.artifact_contract?.artifact_set_id || "unknown";
        const archiveTag = artifactSetId === "unknown" ? null : `brief-artifacts-archive-${artifactSetId}`;
        const archiveUrl = archiveTag ? `https://github.com/${repo}/releases/tag/${archiveTag}` : null;
        const warnings = Array.isArray(summary.warnings) ? summary.warnings : [];
        const validation = summary.validation || {};
        const enrichment = summary.enrichment_contract || {};
        const teams = Array.isArray(summary.teams) ? summary.teams.join(" vs ") : "unknown";

        elements.publishedSummaryPanel.innerHTML = `
            <div class="message-block">
                <div class="button-row">
                    ${badgeHtml(`artifact set ${artifactSetId}`, "info")}
                    ${badgeHtml(freshnessLabel(summary.generated_at), freshnessTone(summary.generated_at))}
                    ${badgeHtml(summary.artifact_contract?.publishable ? "publishable" : "non-publishable", summary.artifact_contract?.publishable ? "success" : "warning")}
                </div>
                <div class="kv">
                    ${kvRow("Generated", `${formatDateTime(summary.generated_at)} (${relativeTime(summary.generated_at)})`)}
                    ${kvRow("Teams", teams)}
                    ${kvRow("Verification", `${validation.verification_fail_count ?? "?"} fail / ${validation.verification_warning_count ?? "?"} warn`)}
                    ${kvRow("Enrichment", enrichment.artifact_status || "unknown")}
                    ${kvRow("Smoke brief", booleanLabel(validation.smoke_brief_passed))}
                </div>
            </div>
            <div class="message-block">
                <h3>Release posture</h3>
                <ul class="list">
                    <li>Rolling release is the current last-known-good source for consumer defaults.</li>
                    <li>Archive release preserves one immutable publishable run for rollback.</li>
                    <li>${warnings.length ? `${warnings.length} warning(s) are recorded in the published summary.` : "No warnings are recorded in the published summary."}</li>
                </ul>
                <div class="asset-actions">
                    <a class="button secondary" href="${escapeAttribute(release.html_url || rollingUrl)}" target="_blank" rel="noreferrer">Rolling release</a>
                    ${
                        archiveUrl
                            ? `<a class="button ghost" href="${escapeAttribute(archiveUrl)}" target="_blank" rel="noreferrer">Archive release</a>`
                            : ""
                    }
                </div>
            </div>
            ${
                warnings.length
                    ? `
                        <div class="message-block warning">
                            <h3>Published warnings</h3>
                            <ul class="list">${warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>
                        </div>
                    `
                    : ""
            }
        `;
    }

    const assets = Array.isArray(release.assets) ? release.assets : [];
    if (!assets.length) {
        elements.assetPanel.innerHTML = renderEmptyState("No release assets are attached to the rolling release.");
        return;
    }

    elements.assetPanel.innerHTML = assets
        .map((asset) => {
            const label = assetLabel(asset.name);
            return `
                <article class="asset-card">
                    <h3>${escapeHtml(label)}</h3>
                    <p class="muted mono">${escapeHtml(asset.name)}</p>
                    <div class="asset-actions">
                        <a class="button secondary" href="${escapeAttribute(asset.browser_download_url || release.html_url)}" target="_blank" rel="noreferrer">Download</a>
                        <a class="button ghost" href="${escapeAttribute(release.html_url || rollingUrl)}" target="_blank" rel="noreferrer">Open release</a>
                    </div>
                </article>
            `;
        })
        .join("");
}

function renderOverviewCards(runsResult, publishedResult, repo, season) {
    refreshQuickLinks();

    if (runsResult.status === "fulfilled" && runsResult.value.runs.length) {
        const latestRun = runsResult.value.runs[0];
        elements.latestRunCard.innerHTML = `
            <div class="metric-title">Latest workflow run</div>
            <div class="metric-value">${escapeHtml(workflowLabel(latestRun))}</div>
            <div class="metric-subtitle">${escapeHtml(latestRun.display_title || "Brief Live Refresh")}</div>
            <div>${badgeHtml(latestRun.event || "unknown", "info")} ${badgeHtml(relativeTime(latestRun.updated_at), workflowTone(latestRun))}</div>
            <div class="kv">
                ${kvRow("Updated", formatDateTime(latestRun.updated_at))}
                ${kvRow("Actor", latestRun.actor?.login || "unknown")}
                ${kvRow("Branch", latestRun.head_branch || "main")}
            </div>
        `;
    } else {
        elements.latestRunCard.innerHTML = renderMetricFallback(
            "Latest workflow run",
            "Unavailable",
            runsResult.status === "rejected"
                ? formatError(runsResult.reason)
                : "No runs are visible yet.",
        );
    }

    if (publishedResult.status === "fulfilled" && publishedResult.value.summary) {
        const summary = publishedResult.value.summary;
        const artifactSetId = summary.artifact_contract?.artifact_set_id || "unknown";
        elements.publishedCard.innerHTML = `
            <div class="metric-title">Published last-known-good</div>
            <div class="metric-value mono">${escapeHtml(artifactSetId)}</div>
            <div class="metric-subtitle">Rolling release for season ${escapeHtml(String(season))}</div>
            <div>${badgeHtml(summary.artifact_contract?.publishable ? "publishable" : "non-publishable", summary.artifact_contract?.publishable ? "success" : "warning")}</div>
            <div class="kv">
                ${kvRow("Generated", formatDateTime(summary.generated_at))}
                ${kvRow("Verification", `${summary.validation?.verification_fail_count ?? "?"} fail / ${summary.validation?.verification_warning_count ?? "?"} warn`)}
                ${kvRow("Release", `<a class="text-link" href="${escapeAttribute(`https://github.com/${repo}/releases/tag/brief-artifacts-${season}`)}" target="_blank" rel="noreferrer">brief-artifacts-${escapeHtml(String(season))}</a>`)}
            </div>
        `;
    } else {
        elements.publishedCard.innerHTML = renderMetricFallback(
            "Published last-known-good",
            "Unavailable",
            publishedResult.status === "rejected"
                ? formatError(publishedResult.reason)
                : "No published summary asset was found.",
        );
    }

    if (publishedResult.status === "fulfilled" && publishedResult.value.summary) {
        const summary = publishedResult.value.summary;
        elements.freshnessCard.innerHTML = `
            <div class="metric-title">Freshness</div>
            <div class="metric-value">${escapeHtml(freshnessLabel(summary.generated_at))}</div>
            <div class="metric-subtitle">Based on pipeline summary \`generated_at\`</div>
            <div>${badgeHtml(relativeTime(summary.generated_at), freshnessTone(summary.generated_at))}</div>
            <div class="kv">
                ${kvRow("Generated at", formatDateTime(summary.generated_at))}
                ${kvRow("Policy", "warn > 36h / critical > 72h")}
            </div>
        `;
    } else {
        elements.freshnessCard.innerHTML = renderMetricFallback(
            "Freshness",
            "Unknown",
            "Load a published summary to compute release freshness.",
        );
    }

    elements.operatorNoteCard.innerHTML = renderOperatorNote(runsResult, publishedResult, repo, season);

    const badges = [];
    if (runsResult.status === "fulfilled" && runsResult.value.runs.length) {
        badges.push(badgeHtml(workflowLabel(runsResult.value.runs[0]), workflowTone(runsResult.value.runs[0])));
    } else {
        badges.push(badgeHtml("workflow unknown", "neutral"));
    }
    if (publishedResult.status === "fulfilled" && publishedResult.value.summary) {
        const summary = publishedResult.value.summary;
        badges.push(badgeHtml(freshnessLabel(summary.generated_at), freshnessTone(summary.generated_at)));
        badges.push(
            badgeHtml(
                summary.artifact_contract?.published_set_complete ? "published set complete" : "published set incomplete",
                summary.artifact_contract?.published_set_complete ? "success" : "warning",
            ),
        );
    } else {
        badges.push(badgeHtml("published summary unavailable", "warning"));
    }
    elements.statusStrip.innerHTML = badges.join("");
}

function renderOperatorNote(runsResult, publishedResult, repo, season) {
    const noteParts = [];

    if (runsResult.status === "fulfilled" && runsResult.value.runs.length) {
        const latestRun = runsResult.value.runs[0];
        if (latestRun.status !== "completed") {
            noteParts.push("A run is still in flight, so the rolling release remains the last-known-good source until publication finishes.");
        } else if (latestRun.conclusion !== "success") {
            noteParts.push("The latest workflow run is not healthy. Consumers should still trust the rolling release, not the newest failed run.");
        } else {
            noteParts.push("The latest workflow run is healthy. The rolling release should reflect the current last-known-good artifact set for this season.");
        }
    } else {
        noteParts.push("Workflow data is unavailable, so treat the rolling release as the authoritative operator view.");
    }

    if (publishedResult.status === "fulfilled" && publishedResult.value.summary) {
        const summary = publishedResult.value.summary;
        const warnings = Array.isArray(summary.warnings) ? summary.warnings.length : 0;
        if (warnings) {
            noteParts.push(`The published summary still carries ${warnings} warning(s), so operators should check the warning list before treating the run as routine.`);
        } else {
            noteParts.push("The published summary has no recorded warnings.");
        }
    } else {
        noteParts.push("The published summary could not be loaded through the Mac mini relay.");
    }

    noteParts.push("Current production-ready support scope is Big Ten teams, Notre Dame, and Utah. Other teams may still run, but should be treated as exploratory until broader readiness work lands.");

    return `
        <div class="metric-title">Operator note</div>
        <div class="metric-value">Current vs last-known-good</div>
        <div class="metric-subtitle">This page does not create its own state model or broaden the current support promise.</div>
        <div class="message-block">
            <p>${escapeHtml(noteParts.join(" "))}</p>
            <div class="asset-actions">
                <a class="button secondary" href="${escapeAttribute(WORKFLOW_PAGE(repo))}" target="_blank" rel="noreferrer">Workflow page</a>
                <a class="button ghost" href="${escapeAttribute(`https://github.com/${repo}/releases/tag/brief-artifacts-${season}`)}" target="_blank" rel="noreferrer">Rolling release</a>
            </div>
        </div>
    `;
}

function refreshQuickLinks() {
    const repo = normalizedRepo();
    const season = normalizedSeason();
    const rollingRelease = `https://github.com/${repo}/releases/tag/brief-artifacts-${season}`;
    const links = [
        {
            title: "Workflow",
            body: "Open the underlying GitHub Actions workflow and its manual dispatch UI.",
            href: WORKFLOW_PAGE(repo),
        },
        {
            title: "Rolling release",
            body: "Inspect the current last-known-good published artifact set for this season.",
            href: rollingRelease,
        },
        {
            title: "All releases",
            body: "See both rolling and archived artifact releases for rollback history.",
            href: RELEASES_PAGE(repo),
        },
        {
            title: "Runbook",
            body: "Operator instructions for live refresh, publication, freshness, and rollback.",
            href: RUNBOOK_PAGE(repo),
        },
        {
            title: "Launch policy",
            body: "Supported scope, launcher defaults, and the official operator path for v1.",
            href: LAUNCH_POLICY_PAGE(repo),
        },
        {
            title: "Warning review",
            body: "How to interpret parity gaps, enrichment issues, and runtime warnings before delivery.",
            href: WARNING_REVIEW_PAGE(repo),
        },
        {
            title: "Published contract",
            body: "Machine-readable artifact expectations and the season release contract.",
            href: CONTRACT_PAGE(repo),
        },
        {
            title: "Enrichment contract",
            body: "What enrichment is allowed to do, when it is required, and how missing data is handled.",
            href: ENRICHMENT_CONTRACT_PAGE(repo),
        },
        {
            title: "Alerts thread",
            body: "Jump into the scheduled-run alert issue if the overnight job is unhealthy.",
            href: ALERTS_PAGE(repo),
        },
    ];

    elements.quickLinksPanel.innerHTML = links
        .map(
            (link) => `
                <article class="link-card">
                    <h3>${escapeHtml(link.title)}</h3>
                    <p class="muted">${escapeHtml(link.body)}</p>
                    <div class="link-actions">
                        <a class="button ghost" href="${escapeAttribute(link.href)}" target="_blank" rel="noreferrer">Open</a>
                    </div>
                </article>
            `,
        )
        .join("");
}

function renderMetricFallback(title, value, detail) {
    return `
        <div class="metric-title">${escapeHtml(title)}</div>
        <div class="metric-value">${escapeHtml(value)}</div>
        <div class="metric-subtitle">${escapeHtml(detail)}</div>
    `;
}

function renderErrorBlock(message) {
    return `<div class="message-block error"><p>${message}</p></div>`;
}

function renderEmptyState(message) {
    return `<div class="empty-state"><p>${escapeHtml(message)}</p></div>`;
}

function kvRow(label, value) {
    return `
        <div class="kv-row">
            <span class="kv-label">${escapeHtml(label)}</span>
            <span class="kv-value">${value}</span>
        </div>
    `;
}

function badgeHtml(label, tone = "neutral") {
    return `<span class="badge badge-${escapeAttribute(tone)}">${escapeHtml(label)}</span>`;
}

function booleanLabel(value) {
    if (value === true) {
        return "true";
    }
    if (value === false) {
        return "false";
    }
    return "unknown";
}

function workflowLabel(run) {
    if (run.status !== "completed") {
        return run.status || "in_progress";
    }
    return run.conclusion || "completed";
}

function workflowTone(run) {
    if (run.status !== "completed") {
        return "info";
    }
    if (run.conclusion === "success") {
        return "success";
    }
    if (run.conclusion === "cancelled" || run.conclusion === "skipped") {
        return "warning";
    }
    return "danger";
}

function freshnessLabel(timestamp) {
    const status = freshnessTone(timestamp);
    if (status === "success") {
        return "fresh";
    }
    if (status === "warning") {
        return "stale warning";
    }
    if (status === "danger") {
        return "stale critical";
    }
    return "unknown";
}

function freshnessTone(timestamp) {
    const generatedAt = timestamp ? new Date(timestamp) : null;
    if (!generatedAt || Number.isNaN(generatedAt.getTime())) {
        return "neutral";
    }
    const ageHours = (Date.now() - generatedAt.getTime()) / 3600000;
    if (ageHours <= 36) {
        return "success";
    }
    if (ageHours <= 72) {
        return "warning";
    }
    return "danger";
}

function assetLabel(filename) {
    if (filename.startsWith("pbp_stats_bundle_")) {
        return "Bundle";
    }
    if (filename.startsWith("cfbstats_verification_")) {
        return "Verification report";
    }
    if (filename.startsWith("cfbstats_")) {
        return "CFBStats snapshot";
    }
    if (filename.startsWith("game_prep_pipeline_summary_")) {
        return "Pipeline summary";
    }
    return filename;
}

function normalizedRepo() {
    return DEFAULTS.repo;
}

function normalizedSeason() {
    return elements.seasonInput.value.trim() || DEFAULTS.season;
}

function setLoadingState(isLoading) {
    loading = isLoading;
    syncActionButtons();
    if (isLoading) {
        elements.statusStrip.innerHTML = badgeHtml("Refreshing dashboard…", "neutral");
    }
}

function syncActionButtons() {
    elements.refreshButton.disabled = loading;
    elements.dispatchButton.disabled = loading;
}

function downloadProxyUrl(pathOrUrl, filename, accept = "application/octet-stream") {
    const params = new URLSearchParams({
        pathOrUrl,
        filename,
        accept,
    });
    return `/api/operator/download?${params.toString()}`;
}

function setInlineMessage(target, message, tone = "neutral") {
    target.innerHTML = message
        ? `<div class="message-block ${escapeAttribute(tone)}"><p>${escapeHtml(message)}</p></div>`
        : "";
}

function formatDateTime(timestamp) {
    if (!timestamp) {
        return "unknown";
    }
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) {
        return String(timestamp);
    }
    return new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
    }).format(date);
}

function formatBytes(value) {
    const bytes = Number(value);
    if (!Number.isFinite(bytes) || bytes < 0) {
        return "unknown";
    }
    if (bytes < 1024) {
        return `${bytes} B`;
    }
    if (bytes < 1024 * 1024) {
        return `${(bytes / 1024).toFixed(1)} KB`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function relativeTime(timestamp) {
    if (!timestamp) {
        return "unknown";
    }
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) {
        return "unknown";
    }
    const deltaSeconds = Math.round((date.getTime() - Date.now()) / 1000);
    const units = [
        ["day", 86400],
        ["hour", 3600],
        ["minute", 60],
    ];
    for (const [unit, size] of units) {
        if (Math.abs(deltaSeconds) >= size || unit === "minute") {
            return new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(
                Math.round(deltaSeconds / size),
                unit,
            );
        }
    }
    return "just now";
}

function formatError(error) {
    if (!error) {
        return "Unknown error.";
    }
    if (error instanceof Error) {
        return error.message;
    }
    return String(error);
}

function encodeRepo(repo) {
    return repo
        .split("/")
        .map((part) => encodeURIComponent(part))
        .join("/");
}

function loadJsonStorage(key) {
    const raw = localStorage.getItem(key);
    if (!raw) {
        return null;
    }
    try {
        return JSON.parse(raw);
    } catch (_error) {
        return null;
    }
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function escapeAttribute(value) {
    return escapeHtml(value);
}

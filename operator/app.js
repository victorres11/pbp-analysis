const DEFAULTS = {
    repo: "victorres11/pbp-analysis",
    workflowFile: "brief-live-refresh.yml",
    team1: "Washington",
    team2: "Ohio State",
    season: "2025",
    lastN: "3",
    briefFormat: "markdown",
    runTests: false,
    strictVerification: true,
    includeEnrichment: true,
};

const STORAGE_KEYS = {
    repo: "brief-operator-repo",
    token: "brief-operator-token",
    dispatch: "brief-operator-dispatch",
};

const WORKFLOW_PAGE = (repo) => `https://github.com/${repo}/actions/workflows/${DEFAULTS.workflowFile}`;
const RELEASES_PAGE = (repo) => `https://github.com/${repo}/releases`;
const RUNBOOK_PAGE = (repo) => `https://github.com/${repo}/blob/main/docs/demo-runbook.md`;
const CONTRACT_PAGE = (repo) => `https://github.com/${repo}/blob/main/docs/published-artifact-contract.md`;
const READINESS_PAGE = (repo) => `https://github.com/${repo}/blob/main/docs/bigten-nd-readiness-matrix.md`;
const TRIAGE_PAGE = (repo) => `https://github.com/${repo}/blob/main/docs/bigten-nd-warning-triage.md`;
const ALERTS_PAGE = (repo) =>
    `https://github.com/${repo}/issues?q=is%3Aissue%20state%3Aopen%20%22Brief%20Live%20Refresh%20Alerts%22`;

const elements = {};
let loading = false;

document.addEventListener("DOMContentLoaded", () => {
    cacheElements();
    hydrateSettings();
    bindEvents();
    refreshDashboard();
});

function cacheElements() {
    for (const id of [
        "repoInput",
        "tokenInput",
        "team1Input",
        "team2Input",
        "seasonInput",
        "lastNInput",
        "briefFormatInput",
        "runTestsInput",
        "strictVerificationInput",
        "includeEnrichmentInput",
        "saveTokenButton",
        "clearTokenButton",
        "refreshButton",
        "dispatchButton",
        "settingsMessage",
        "dispatchMessage",
        "statusStrip",
        "latestRunCard",
        "publishedCard",
        "freshnessCard",
        "operatorNoteCard",
        "runsPanel",
        "publishedSummaryPanel",
        "assetPanel",
        "quickLinksPanel",
        "workflowLink",
        "rollingReleaseLink",
        "settingsForm",
        "dispatchForm",
    ]) {
        elements[id] = document.getElementById(id);
    }
}

function hydrateSettings() {
    const savedRepo = localStorage.getItem(STORAGE_KEYS.repo);
    const savedToken = localStorage.getItem(STORAGE_KEYS.token);
    const savedDispatch = loadJsonStorage(STORAGE_KEYS.dispatch);

    if (savedRepo) {
        elements.repoInput.value = savedRepo;
    }
    if (savedToken) {
        elements.tokenInput.value = savedToken;
        setInlineMessage(
            elements.settingsMessage,
            "Using a token saved in this browser. You can still overwrite it for the current session.",
            "success",
        );
    }
    if (savedDispatch) {
        elements.team1Input.value = savedDispatch.team1 || DEFAULTS.team1;
        elements.team2Input.value = savedDispatch.team2 || DEFAULTS.team2;
        elements.seasonInput.value = savedDispatch.season || DEFAULTS.season;
        elements.lastNInput.value = savedDispatch.lastN || DEFAULTS.lastN;
        elements.briefFormatInput.value = savedDispatch.briefFormat || DEFAULTS.briefFormat;
        elements.runTestsInput.checked = Boolean(savedDispatch.runTests);
        elements.strictVerificationInput.checked = savedDispatch.strictVerification !== false;
        elements.includeEnrichmentInput.checked = savedDispatch.includeEnrichment !== false;
    }
}

function bindEvents() {
    elements.refreshButton.addEventListener("click", () => refreshDashboard());
    elements.saveTokenButton.addEventListener("click", saveTokenLocally);
    elements.clearTokenButton.addEventListener("click", clearSavedToken);
    elements.settingsForm.addEventListener("submit", (event) => event.preventDefault());
    elements.dispatchForm.addEventListener("submit", handleDispatch);

    elements.repoInput.addEventListener("change", handleRepoChanged);
    elements.seasonInput.addEventListener("change", handleDispatchSettingsChanged);
    elements.tokenInput.addEventListener("input", syncActionButtons);

    for (const field of [
        elements.team1Input,
        elements.team2Input,
        elements.lastNInput,
        elements.briefFormatInput,
        elements.runTestsInput,
        elements.strictVerificationInput,
        elements.includeEnrichmentInput,
    ]) {
        field.addEventListener("change", persistDispatchSettings);
    }
}

function handleRepoChanged() {
    localStorage.setItem(STORAGE_KEYS.repo, normalizedRepo());
    refreshQuickLinks();
}

function handleDispatchSettingsChanged() {
    persistDispatchSettings();
    refreshQuickLinks();
}

function persistDispatchSettings() {
    localStorage.setItem(
        STORAGE_KEYS.dispatch,
        JSON.stringify({
            team1: elements.team1Input.value.trim() || DEFAULTS.team1,
            team2: elements.team2Input.value.trim() || DEFAULTS.team2,
            season: elements.seasonInput.value.trim() || DEFAULTS.season,
            lastN: elements.lastNInput.value.trim() || DEFAULTS.lastN,
            briefFormat: elements.briefFormatInput.value,
            runTests: elements.runTestsInput.checked,
            strictVerification: elements.strictVerificationInput.checked,
            includeEnrichment: elements.includeEnrichmentInput.checked,
        }),
    );
}

function saveTokenLocally() {
    const token = elements.tokenInput.value.trim();
    if (!token) {
        setInlineMessage(elements.settingsMessage, "Paste a token before saving it locally.", "warning");
        return;
    }
    localStorage.setItem(STORAGE_KEYS.token, token);
    syncActionButtons();
    setInlineMessage(elements.settingsMessage, "Saved token in this browser for future dashboard sessions.", "success");
}

function clearSavedToken() {
    localStorage.removeItem(STORAGE_KEYS.token);
    elements.tokenInput.value = "";
    syncActionButtons();
    setInlineMessage(elements.settingsMessage, "Cleared the saved token. The dashboard is back in read-only/session mode.", "warning");
}

async function handleDispatch(event) {
    event.preventDefault();

    const token = elements.tokenInput.value.trim();
    if (!token) {
        setInlineMessage(
            elements.dispatchMessage,
            "Dispatch needs a GitHub token. Add one above, then try again.",
            "warning",
        );
        return;
    }

    const repo = normalizedRepo();
    const inputs = {
        team1: elements.team1Input.value.trim() || DEFAULTS.team1,
        team2: elements.team2Input.value.trim() || DEFAULTS.team2,
        season: elements.seasonInput.value.trim() || DEFAULTS.season,
        last_n: elements.lastNInput.value.trim() || DEFAULTS.lastN,
        brief_format: elements.briefFormatInput.value || DEFAULTS.briefFormat,
        run_tests: String(elements.runTestsInput.checked),
        strict_verification: String(elements.strictVerificationInput.checked),
        include_enrichment: String(elements.includeEnrichmentInput.checked),
    };
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
                token,
                body: {
                    ref: "main",
                    inputs,
                },
            },
        );
        setInlineMessage(
            elements.dispatchMessage,
            `Dispatch accepted by GitHub. The new run should appear in a few seconds. Manual runs still publish only if they stay healthy and publishable.`,
            "success",
        );
        window.setTimeout(() => refreshDashboard({ quiet: true }), 5000);
    } catch (error) {
        setInlineMessage(elements.dispatchMessage, formatError(error), "error");
    } finally {
        syncActionButtons();
    }
}

async function refreshDashboard({ quiet = false } = {}) {
    const repo = normalizedRepo();
    const season = normalizedSeason();
    const token = elements.tokenInput.value.trim();

    localStorage.setItem(STORAGE_KEYS.repo, repo);
    persistDispatchSettings();

    refreshQuickLinks();
    setLoadingState(true);

    const [runsResult, publishedResult] = await Promise.allSettled([
        fetchWorkflowRuns(repo, token),
        fetchPublishedSeason(repo, season, token),
    ]);

    renderLatestRunBlock(runsResult, repo);
    renderPublishedBlock(publishedResult, repo, season);
    renderOverviewCards(runsResult, publishedResult, repo, season);

    if (!quiet) {
        const successCount = [runsResult, publishedResult].filter((result) => result.status === "fulfilled").length;
        const message =
            successCount === 2
                ? "Dashboard refreshed from GitHub."
                : "Dashboard refreshed with partial data. Add a token if you need private workflow or release access.";
        const tone = successCount === 2 ? "success" : "warning";
        setInlineMessage(elements.settingsMessage, message, tone);
    }

    setLoadingState(false);
}

async function fetchWorkflowRuns(repo, token) {
    const payload = await githubRequest(
        `/repos/${encodeRepo(repo)}/actions/workflows/${encodeURIComponent(DEFAULTS.workflowFile)}/runs?per_page=8`,
        { token },
    );
    return {
        workflowUrl: WORKFLOW_PAGE(repo),
        runs: Array.isArray(payload.workflow_runs) ? payload.workflow_runs : [],
    };
}

async function fetchPublishedSeason(repo, season, token) {
    const tag = `brief-artifacts-${season}`;
    const release = await githubRequest(`/repos/${encodeRepo(repo)}/releases/tags/${encodeURIComponent(tag)}`, {
        token,
    });
    const summaryFilename = `game_prep_pipeline_summary_${season}.json`;
    const summaryAsset = Array.isArray(release.assets)
        ? release.assets.find((asset) => asset && asset.name === summaryFilename)
        : null;

    let summary = null;
    if (summaryAsset && typeof summaryAsset.url === "string") {
        summary = await githubRequest(summaryAsset.url, {
            token,
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

async function githubRequest(pathOrUrl, { method = "GET", token = "", accept = "application/vnd.github+json", body } = {}) {
    const url = pathOrUrl.startsWith("http") ? pathOrUrl : `https://api.github.com${pathOrUrl}`;
    const headers = {
        Accept: accept,
        "X-GitHub-Api-Version": "2022-11-28",
    };
    if (token) {
        headers.Authorization = `Bearer ${token}`;
    }
    if (body !== undefined) {
        headers["Content-Type"] = "application/json";
    }

    const response = await fetch(url, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
    });

    if (response.status === 204) {
        return null;
    }

    if (!response.ok) {
        const message = await extractErrorMessage(response);
        throw new Error(message);
    }

    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json") || contentType.includes("application/octet-stream")) {
        return response.json();
    }
    return response.text();
}

async function extractErrorMessage(response) {
    const fallback = `GitHub API request failed (${response.status} ${response.statusText})`;
    try {
        const text = await response.text();
        if (!text) {
            return fallback;
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
        noteParts.push("The published summary could not be loaded. A token may be required if the repo or release is private.");
    }

    noteParts.push("Current production-ready support scope is Big Ten teams plus Notre Dame. Other teams may still run, but should be treated as exploratory until broader readiness work lands.");

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
            title: "Published contract",
            body: "Machine-readable artifact expectations and the season release contract.",
            href: CONTRACT_PAGE(repo),
        },
        {
            title: "Readiness matrix",
            body: "Current Big Ten + Notre Dame support coverage and readiness posture.",
            href: READINESS_PAGE(repo),
        },
        {
            title: "Warning triage",
            body: "Operator severity guide for must-fix gaps, known gaps, and noise.",
            href: TRIAGE_PAGE(repo),
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
    return (elements.repoInput.value.trim() || DEFAULTS.repo).replace(/^https:\/\/github\.com\//, "").replace(/\/+$/, "");
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
    elements.dispatchButton.disabled = loading || !elements.tokenInput.value.trim();
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

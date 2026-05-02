const body = document.body;
const page = body.dataset.page;
const template = document.getElementById("video-card-template");
const modalEl = document.getElementById("player-modal");
const closePlayerButton = document.getElementById("close-player");
const videoPlayer = document.getElementById("video-player");
const playerTitle = document.getElementById("player-title");
const playerCategory = document.getElementById("player-category");
const deleteVideoButton = document.getElementById("delete-video-button");
const deleteStatusEl = document.getElementById("delete-status");
const randomPlayButton = document.getElementById("random-play");
const hostToggleButton = document.getElementById("host-toggle");
const autoDeleteToggle = document.getElementById("auto-delete-toggle");
const logoutButton = document.getElementById("logout-button");
const shuffleControlsEl = document.getElementById("shuffle-controls");
const shuffleSummaryEl = document.getElementById("shuffle-summary");
const shuffleSubcategoriesEl = document.getElementById("shuffle-subcategories");
const shuffleSelectAllButton = document.getElementById("shuffle-select-all");
const shuffleClearAllButton = document.getElementById("shuffle-clear-all");
const infoGridEl = document.getElementById("info-grid");
const continueWatchingEl = document.getElementById("continue-watching");
const manageWatchedListEl = document.getElementById("manage-watched-list");
const clearWatchedButton = document.getElementById("clear-watched-button");
const gateOverlay = document.getElementById("gate-overlay");
const startupScreen = document.getElementById("startup-screen");
const startupIntro = document.getElementById("startup-intro");
const startupFallback = document.getElementById("startup-fallback");
const profileScreen = document.getElementById("profile-screen");
const passwordScreen = document.getElementById("password-screen");
const profileButton = document.getElementById("profile-button");
const passwordForm = document.getElementById("password-form");
const passwordInput = document.getElementById("password-input");
const passwordError = document.getElementById("password-error");
const backToProfileButton = document.getElementById("back-to-profile");

const HISTORY_COOKIE = "metflix_history";
const AUTO_DELETE_COOKIE = "metflix_auto_delete";
const HISTORY_MAX_ENTRIES = 30;
const TITLE_SOFT_LIMIT = 30;
const REMOVED_TITLE_KEYWORDS = new Set(["1boy", "1girl", "1girls", "2d", "3d", "boy", "girl", "girls", "d", "rx"]);
const TRAILING_KEYWORD_MAP = new Map([
  ["fpsblyck", "Fpsblyck"],
  ["softshikioni", "Softshikioni"],
  ["sunfanart", "Sunfanart"],
  ["suuru", "Suuru"],
  ["z1g3d", "Z1g3d"],
]);
const AUTO_DELETE_DELAY_MS = 15000;

let library = null;
let activeVideo = null;
let progressSaveTimer = 0;
let isUnlocked = false;
let autoDeleteTimer = 0;
let pendingAutoDeleteVideoId = "";
let selectedShuffleKeys = new Set();
let shuffleSelectionInitialized = false;
let thumbnailObserver = null;
let activeThumbnailJobs = 0;
let startupTransitionTimer = 0;
const pendingThumbnailQueue = [];
const thumbnailCache = new Map();
const THUMBNAIL_WIDTH = 256;
const THUMBNAIL_HEIGHT = 144;
const THUMBNAIL_QUALITY = 0.52;
const MAX_THUMBNAIL_JOBS = 2;

function getCookie(name) {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : "";
}

function setCookie(name, value, days = 365) {
  const expires = new Date(Date.now() + days * 24 * 60 * 60 * 1000).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Lax`;
}

function autoDeleteEnabled() {
  return getCookie(AUTO_DELETE_COOKIE) === "1";
}

function setAutoDeleteEnabled(enabled) {
  setCookie(AUTO_DELETE_COOKIE, enabled ? "1" : "0");
}

function loadHistory() {
  try {
    const raw = getCookie(HISTORY_COOKIE);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    return typeof parsed === "object" && parsed ? parsed : {};
  } catch {
    return {};
  }
}

function saveHistory(history) {
  const entries = Object.entries(history)
    .sort((a, b) => (b[1]?.updated_at || 0) - (a[1]?.updated_at || 0))
    .slice(0, HISTORY_MAX_ENTRIES);
  setCookie(HISTORY_COOKIE, JSON.stringify(Object.fromEntries(entries)));
}

function removeHistoryItem(videoId) {
  const history = loadHistory();
  delete history[videoId];
  saveHistory(history);
}

function clearWatchedHistory() {
  const history = loadHistory();
  Object.keys(history).forEach((videoId) => {
    if (history[videoId]?.watched) {
      delete history[videoId];
    }
  });
  saveHistory(history);
}

function updateHistory(video, patch) {
  if (!video?.id) {
    return;
  }
  const history = loadHistory();
  const current = history[video.id] || {};
  history[video.id] = {
    title: video.title,
    main_category: video.main_category,
    subcategory: video.subcategory,
    duration: patch.duration ?? current.duration ?? 0,
    position: patch.position ?? current.position ?? 0,
    watch_count: patch.watch_count ?? current.watch_count ?? 0,
    watched: patch.watched ?? current.watched ?? false,
    updated_at: Date.now(),
  };
  saveHistory(history);
}

function historyFor(videoId) {
  return loadHistory()[videoId] || null;
}

function watchedPercent(video) {
  const entry = historyFor(video.id);
  if (!entry || !entry.duration) {
    return 0;
  }
  return Math.max(0, Math.min(1, entry.position / entry.duration));
}

function isWatched(video) {
  const entry = historyFor(video.id);
  return Boolean(entry?.watched || watchedPercent(video) >= 0.9);
}

function getWatchCount(video) {
  return historyFor(video.id)?.watch_count || 0;
}

function truncateTitle(title, maxLength = 20) {
  if (!title || title.length < TITLE_SOFT_LIMIT) {
    return title;
  }
  return `${title.slice(0, maxLength - 3)}...`;
}

function prettyLabel(value) {
  if (!value) {
    return "";
  }
  const normalized = value.replace(/\.[^/.]+$/, "").replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
  return normalized ? normalized.charAt(0).toUpperCase() + normalized.slice(1) : "";
}

function prettyTitle(value) {
  if (!value) {
    return "";
  }
  const source = value.replace(/\.[^/.]+$/, "");
  const bracketNumbers = [];
  source.replace(/[\[(]([^\])]+)[\])]/g, (_, inner) => {
    const numbers = inner.match(/\d+/g);
    if (numbers) {
      bracketNumbers.push(...numbers);
    }
    return _;
  });

  let normalized = source;
  normalized = normalized.replace(/[\[(][^\])]*[\])]/g, " ");
  normalized = normalized.replace(/ai[\s_-]*generated/gi, " ");
  normalized = normalized.replace(/[_-]+/g, " ").trim();

  const suffixKeywords = [];
  const seenSuffixKeywords = new Set();
  const mainTokens = [];

  normalized.split(/\s+/).filter(Boolean).forEach((token) => {
    const lower = token.toLowerCase();
    if (TRAILING_KEYWORD_MAP.has(lower)) {
      if (!seenSuffixKeywords.has(lower)) {
        seenSuffixKeywords.add(lower);
        suffixKeywords.push(TRAILING_KEYWORD_MAP.get(lower));
      }
      return;
    }
    const withoutNumbers = token.replace(/\d+/g, "");
    const strippedLower = withoutNumbers.toLowerCase();
    if (!withoutNumbers || REMOVED_TITLE_KEYWORDS.has(lower) || REMOVED_TITLE_KEYWORDS.has(strippedLower)) {
      return;
    }
    mainTokens.push(withoutNumbers);
  });

  const mainTitle = mainTokens.join(" ").replace(/\s+/g, " ").trim();
  const titledMain = mainTitle ? mainTitle.charAt(0).toUpperCase() + mainTitle.slice(1) : "";
  if (!titledMain && suffixKeywords.length) {
    const postLabel = bracketNumbers.length ? `Post(${bracketNumbers.join(", ")})` : "Post";
    return `${postLabel} - ${suffixKeywords.join(" - ")}`;
  }
  return suffixKeywords.length ? `${titledMain} - ${suffixKeywords.join(" - ")}` : titledMain;
}

function pluralize(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

async function checkSession() {
  try {
    const payload = await fetchJSON("/api/session");
    return Boolean(payload.authenticated);
  } catch {
    return false;
  }
}

function enhanceVideos(data) {
  const allVideos = (data.all_videos || []).map((video) => ({
    ...video,
    watched: isWatched(video),
    watch_count: getWatchCount(video),
    progress: watchedPercent(video),
    shuffle_key: getShuffleKey(video),
    url: `/api/video/${encodeURIComponent(video.id)}`,
  }));

  const byId = Object.fromEntries(allVideos.map((video) => [video.id, video]));
  const mainCategories = (data.main_categories || []).map((mainCategory) => ({
    ...mainCategory,
    featured_videos: (mainCategory.featured_videos || []).map((video) => byId[video.id] || video),
    subcategories: (mainCategory.subcategories || []).map((subcategory) => ({
      ...subcategory,
      featured: subcategory.featured ? byId[subcategory.featured.id] || subcategory.featured : null,
      videos: (subcategory.videos || []).map((video) => byId[video.id] || video),
    })),
  }));

  const recommendations = [...allVideos].sort((a, b) => {
    const aWatched = a.watched ? 1 : 0;
    const bWatched = b.watched ? 1 : 0;
    if (aWatched !== bWatched) {
      return aWatched - bWatched;
    }
    const aUpdated = historyFor(a.id)?.updated_at || 0;
    const bUpdated = historyFor(b.id)?.updated_at || 0;
    return bUpdated - aUpdated || Math.random() - 0.5;
  });

  const continueWatching = allVideos.filter((video) => video.progress > 0.02 && video.progress < 0.98);
  return { ...data, all_videos: allVideos, main_categories: mainCategories, recommendations, continueWatching };
}

function setSummary(data) {
  const hosting = document.getElementById("summary-hosting");
  const count = document.getElementById("summary-count");
  const categories = document.getElementById("summary-categories");
  if (!hosting || !count || !categories) {
    return;
  }
  hosting.textContent = data.hosting_enabled ? "Hosting live" : "Hosting paused";
  count.textContent = pluralize(data.video_count || 0, "video");
  categories.textContent = pluralize(data.info?.main_category_count || 0, "category");
}

function createInfoCard(label, value) {
  const article = document.createElement("article");
  article.className = "info-card";
  article.innerHTML = `<p class="info-card__label"></p><h3 class="info-card__value"></h3>`;
  article.querySelector(".info-card__label").textContent = label;
  article.querySelector(".info-card__value").textContent = value || "Unknown";
  return article;
}

function renderInfo(data) {
  if (!infoGridEl) {
    return;
  }
  infoGridEl.innerHTML = "";
  const items = [
    ["Hosting", data.hosting_enabled ? "On" : "Off"],
    ["Backend status", data.backend_connection?.connected ? "Connected" : "Disconnected"],
    ["Backend service", data.backend_connection?.message || data.source_error || "Unknown"],
    ["Backend host", data.info?.backend_host || "Unknown"],
    ["Backend port", data.info?.backend_port ? String(data.info.backend_port) : "Unknown"],
    ["Media library root", data.info?.videos_root || "Not configured"],
    ["Client host", data.info?.client_host || "Unknown"],
    ["Client port", data.info?.client_port ? String(data.info.client_port) : "Unknown"],
    ["Client URL", data.info?.client_url || "Unknown"],
    ["Backend URL", data.info?.backend_url || "Not configured"],
    ["Video count", String(data.video_count || 0)],
    ["Main categories", String(data.info?.main_category_count || 0)],
    ["Subcategories", String(data.info?.subcategory_count || 0)],
  ];
  items.forEach(([label, value]) => infoGridEl.appendChild(createInfoCard(label, value)));
}

function showGateScreen(screen) {
  [startupScreen, profileScreen, passwordScreen].forEach((node) => {
    if (!node) {
      return;
    }
    node.classList.toggle("hidden", node !== screen);
  });
  if (screen !== startupScreen) {
    if (startupTransitionTimer) {
      window.clearTimeout(startupTransitionTimer);
      startupTransitionTimer = 0;
    }
    if (startupIntro) {
      try {
        startupIntro.pause();
      } catch {
        // Ignore media pause errors on navigation.
      }
    }
  }
}

function queueStartupTransition(delay) {
  if (startupTransitionTimer) {
    window.clearTimeout(startupTransitionTimer);
  }
  startupTransitionTimer = window.setTimeout(() => {
    if (!gateOverlay || gateOverlay.classList.contains("hidden") || isUnlocked) {
      return;
    }
    showGateScreen(profileScreen);
  }, delay);
}

function resetStartupIntro() {
  if (!startupIntro) {
    return;
  }
  startupIntro.classList.remove("startup-intro--ready");
  if (startupFallback) {
    startupFallback.hidden = false;
  }
  try {
    startupIntro.pause();
    startupIntro.currentTime = 0;
  } catch {
    // Ignore media reset issues when the browser has not loaded metadata yet.
  }
}

function playStartupIntro() {
  if (!startupIntro) {
    queueStartupTransition(1100);
    return;
  }

  resetStartupIntro();

  const revealIntro = () => {
    startupIntro.classList.add("startup-intro--ready");
    if (startupFallback) {
      startupFallback.hidden = true;
    }
  };

  startupIntro.addEventListener("canplay", revealIntro, { once: true });
  startupIntro.addEventListener("playing", revealIntro, { once: true });
  startupIntro.addEventListener(
    "loadedmetadata",
    () => {
      const durationMs =
        Number.isFinite(startupIntro.duration) && startupIntro.duration > 0
          ? Math.ceil(startupIntro.duration * 1000) + 250
          : 6000;
      queueStartupTransition(durationMs);
    },
    { once: true }
  );
  startupIntro.addEventListener(
    "ended",
    () => {
      queueStartupTransition(0);
    },
    { once: true }
  );
  startupIntro.addEventListener(
    "error",
    () => {
      if (startupFallback) {
        startupFallback.hidden = false;
      }
      queueStartupTransition(1400);
    },
    { once: true }
  );

  queueStartupTransition(6000);
  const playAttempt = startupIntro.play();
  if (playAttempt && typeof playAttempt.catch === "function") {
    playAttempt.catch(() => {
      if (startupFallback) {
        startupFallback.hidden = false;
      }
      queueStartupTransition(1400);
    });
  }
}

async function startGateFlow() {
  if (!gateOverlay) {
    return;
  }

  isUnlocked = await checkSession();
  if (isUnlocked) {
    resetStartupIntro();
    gateOverlay.classList.add("hidden");
    gateOverlay.setAttribute("aria-hidden", "true");
    return;
  }

  gateOverlay.classList.remove("hidden");
  gateOverlay.setAttribute("aria-hidden", "false");
  showGateScreen(startupScreen);
  playStartupIntro();
}

function buildBadgeLabel(video) {
  const main = prettyLabel(video.main_category);
  const sub = prettyLabel(video.subcategory);
  return sub ? `${main} / ${sub}` : main;
}

function displayTitle(video) {
  return prettyTitle(video?.filename || video?.title || "");
}

function getShuffleKey(video) {
  return `${video.main_category}///${video.subcategory}`;
}

function collectShuffleOptions(data) {
  return (data.main_categories || []).flatMap((mainCategory) =>
    (mainCategory.subcategories || []).map((subcategory) => ({
      key: `${mainCategory.name}///${subcategory.name}`,
      main: prettyLabel(mainCategory.name),
      sub: prettyLabel(subcategory.name),
      count: subcategory.video_count || (subcategory.videos || []).length || 0,
    }))
  );
}

function syncShuffleSelection(options) {
  const available = new Set(options.map((option) => option.key));
  if (!shuffleSelectionInitialized) {
    options.forEach((option) => selectedShuffleKeys.add(option.key));
    shuffleSelectionInitialized = true;
    return;
  }
  selectedShuffleKeys = new Set([...selectedShuffleKeys].filter((key) => available.has(key)));
}

function updateShuffleSummary(options) {
  if (!shuffleSummaryEl) {
    return;
  }
  const selectedCount = options.filter((option) => selectedShuffleKeys.has(option.key)).length;
  shuffleSummaryEl.textContent = `${selectedCount} of ${options.length} subcategories included in shuffle.`;
}

function renderShuffleControls(data) {
  if (!shuffleControlsEl || !shuffleSubcategoriesEl || !shuffleSummaryEl) {
    return;
  }
  const options = collectShuffleOptions(data);
  shuffleSubcategoriesEl.innerHTML = "";
  if (!options.length) {
    shuffleSummaryEl.textContent = "No subcategories available yet.";
    return;
  }
  syncShuffleSelection(options);
  updateShuffleSummary(options);

  options.forEach((option) => {
    const label = document.createElement("label");
    label.className = "shuffle-chip";
    label.innerHTML = `
      <input type="checkbox" />
      <span class="shuffle-chip__text">
        <strong></strong>
        <span></span>
      </span>
    `;
    const checkbox = label.querySelector("input");
    checkbox.checked = selectedShuffleKeys.has(option.key);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        selectedShuffleKeys.add(option.key);
      } else {
        selectedShuffleKeys.delete(option.key);
      }
      updateShuffleSummary(options);
    });
    label.querySelector("strong").textContent = option.sub;
    label.querySelector(".shuffle-chip__text span").textContent = `${option.main} | ${pluralize(option.count, "video")}`;
    shuffleSubcategoriesEl.appendChild(label);
  });
}

function ensureThumbnailObserver() {
  if (thumbnailObserver || typeof IntersectionObserver === "undefined") {
    return;
  }
  thumbnailObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) {
        return;
      }
      const imageEl = entry.target;
      thumbnailObserver.unobserve(imageEl);
      queueThumbnailLoad(imageEl);
    });
  }, { rootMargin: "220px 0px" });
}

function finalizeThumbnail(cardEl, imageEl, dataUrl) {
  if (dataUrl) {
    imageEl.src = dataUrl;
  }
  cardEl.dataset.thumbnailReady = "true";
}

function generateThumbnail(sourceUrl) {
  return new Promise((resolve, reject) => {
    const videoEl = document.createElement("video");
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d", { alpha: false });
    let settled = false;

    if (!context) {
      reject(new Error("Canvas is unavailable"));
      return;
    }

    const cleanup = () => {
      videoEl.pause();
      videoEl.removeAttribute("src");
      videoEl.load();
      videoEl.onloadedmetadata = null;
      videoEl.onseeked = null;
      videoEl.onerror = null;
      videoEl.onabort = null;
    };

    const fail = () => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      reject(new Error("Thumbnail generation failed"));
    };

    videoEl.muted = true;
    videoEl.playsInline = true;
    videoEl.preload = "metadata";
    videoEl.src = sourceUrl;

    videoEl.onloadedmetadata = () => {
      if (!Number.isFinite(videoEl.duration) || videoEl.duration <= 0) {
        fail();
        return;
      }
      try {
        videoEl.currentTime = Math.min(1, Math.max(0.05, videoEl.duration * 0.12));
      } catch {
        fail();
      }
    };

    videoEl.onseeked = () => {
      if (settled) {
        return;
      }
      canvas.width = THUMBNAIL_WIDTH;
      canvas.height = THUMBNAIL_HEIGHT;
      context.drawImage(videoEl, 0, 0, THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT);
      settled = true;
      const dataUrl = canvas.toDataURL("image/jpeg", THUMBNAIL_QUALITY);
      cleanup();
      resolve(dataUrl);
    };

    videoEl.onerror = fail;
    videoEl.onabort = fail;
  });
}

function pumpThumbnailQueue() {
  while (activeThumbnailJobs < MAX_THUMBNAIL_JOBS && pendingThumbnailQueue.length) {
    const imageEl = pendingThumbnailQueue.shift();
    if (!imageEl?.isConnected || imageEl.dataset.loading === "done") {
      continue;
    }
    activeThumbnailJobs += 1;
    const cardEl = imageEl.closest(".title-card");
    const sourceUrl = imageEl.dataset.src;
    if (!cardEl || !sourceUrl) {
      activeThumbnailJobs -= 1;
      continue;
    }

    if (thumbnailCache.has(sourceUrl)) {
      finalizeThumbnail(cardEl, imageEl, thumbnailCache.get(sourceUrl));
      imageEl.dataset.loading = "done";
      activeThumbnailJobs -= 1;
      continue;
    }

    generateThumbnail(sourceUrl)
      .then((dataUrl) => {
        thumbnailCache.set(sourceUrl, dataUrl);
        finalizeThumbnail(cardEl, imageEl, dataUrl);
      })
      .catch(() => {
        cardEl.dataset.thumbnailReady = "false";
      })
      .finally(() => {
        imageEl.dataset.loading = "done";
        activeThumbnailJobs -= 1;
        pumpThumbnailQueue();
      });
  }
}

function queueThumbnailLoad(imageEl) {
  if (!imageEl || imageEl.dataset.loading) {
    return;
  }
  imageEl.dataset.loading = "queued";
  pendingThumbnailQueue.push(imageEl);
  pumpThumbnailQueue();
}

function queueThumbnail(imageEl, cardEl, sourceUrl, altText) {
  if (!imageEl || !cardEl || !sourceUrl) {
    return;
  }
  imageEl.alt = altText || "";
  imageEl.dataset.src = sourceUrl;
  if (thumbnailCache.has(sourceUrl)) {
    imageEl.dataset.loading = "done";
    finalizeThumbnail(cardEl, imageEl, thumbnailCache.get(sourceUrl));
    return;
  }
  ensureThumbnailObserver();
  if (thumbnailObserver) {
    thumbnailObserver.observe(imageEl);
  } else {
    queueThumbnailLoad(imageEl);
  }
}

function resetDeleteStatus(message = "") {
  if (deleteStatusEl) {
    deleteStatusEl.textContent = message;
  }
}

function clearRuntimeCaches() {
  cancelAutoDelete();
  window.clearTimeout(progressSaveTimer);
  progressSaveTimer = 0;
  library = null;
  activeVideo = null;
  activeThumbnailJobs = 0;
  pendingThumbnailQueue.length = 0;
  thumbnailCache.clear();
  if (thumbnailObserver) {
    thumbnailObserver.disconnect();
    thumbnailObserver = null;
  }
  if (videoPlayer) {
    videoPlayer.pause();
    videoPlayer.removeAttribute("src");
    videoPlayer.load();
  }
  if (modalEl) {
    modalEl.classList.add("hidden");
    modalEl.setAttribute("aria-hidden", "true");
  }
  resetDeleteStatus("");
}

function cancelAutoDelete() {
  window.clearTimeout(autoDeleteTimer);
  autoDeleteTimer = 0;
  pendingAutoDeleteVideoId = "";
}

function videoLookupById(videoId) {
  return library?.all_videos?.find((video) => video.id === videoId) || null;
}

async function deleteVideo(videoOrId, options = {}) {
  const video = typeof videoOrId === "string" ? videoLookupById(videoOrId) : videoOrId;
  if (!video?.id) {
    throw new Error("Video not found.");
  }

  cancelAutoDelete();
  resetDeleteStatus(options.statusMessage || "");
  await fetchJSON("/api/delete", {
    method: "POST",
    body: JSON.stringify({ video_id: video.id }),
  });
  removeHistoryItem(video.id);

  if (activeVideo?.id === video.id) {
    modalEl?.classList.add("hidden");
    modalEl?.setAttribute("aria-hidden", "true");
    videoPlayer.pause();
    videoPlayer.removeAttribute("src");
    videoPlayer.load();
    activeVideo = null;
  }

  await refreshLibrary();
  resetDeleteStatus("Video deleted.");
}

function scheduleAutoDelete(video) {
  cancelAutoDelete();
  if (!video?.id || !autoDeleteEnabled()) {
    resetDeleteStatus("");
    return;
  }
  pendingAutoDeleteVideoId = video.id;
  resetDeleteStatus("This video will be deleted 15 seconds after close.");
  autoDeleteTimer = window.setTimeout(async () => {
    if (pendingAutoDeleteVideoId !== video.id) {
      return;
    }
    try {
      await deleteVideo(video.id, { statusMessage: "Auto-deleting video..." });
    } catch (error) {
      resetDeleteStatus(error.message);
    }
  }, AUTO_DELETE_DELAY_MS);
}

function createCard(video) {
  const node = template.content.firstElementChild.cloneNode(true);
  node.dataset.thumbnailReady = "false";
  const button = node.querySelector(".title-card__button");
  const thumbImage = node.querySelector(".title-card__thumb");
  const title = node.querySelector(".title-card__title");
  const meta = node.querySelector(".title-card__meta");
  const categoryBadge = node.querySelector(".title-card__badge--category");
  const statusBadge = node.querySelector(".title-card__badge--status");
  const progressBar = node.querySelector(".title-card__progress span");
  const previewLabel = node.querySelector(".title-card__preview-label");

  const prettyVideoTitle = displayTitle(video);
  title.textContent = truncateTitle(prettyVideoTitle);
  title.title = prettyVideoTitle;
  meta.textContent = video.progress > 0.02 && video.progress < 0.98
    ? `Resume at ${Math.round(video.progress * 100)}%`
    : video.watch_count
      ? `${video.watch_count} watch${video.watch_count === 1 ? "" : "es"}`
      : "Ready to watch";

  const badgeLabel = buildBadgeLabel(video);
  categoryBadge.textContent = truncateTitle(badgeLabel, 18);
  categoryBadge.title = badgeLabel;
  statusBadge.textContent = video.watched ? "Watched" : video.progress > 0.02 ? "In progress" : "New";
  statusBadge.dataset.status = video.watched ? "watched" : video.progress > 0.02 ? "progress" : "unwatched";

  previewLabel.textContent = truncateTitle(prettyVideoTitle, 26);
  queueThumbnail(thumbImage, node, video.url, prettyVideoTitle);

  progressBar.style.width = `${Math.round((video.progress || 0) * 100)}%`;
  button.addEventListener("click", () => openPlayer(video));
  return node;
}

function renderRail(target, videos, emptyMessage) {
  if (!target) {
    return;
  }
  target.innerHTML = "";
  if (!videos.length) {
    target.innerHTML = `<div class="empty-state">${emptyMessage}</div>`;
    return;
  }
  videos.forEach((video) => target.appendChild(createCard(video)));
}

function renderBillboard(data) {
  const titleEl = document.getElementById("billboard-title");
  const descriptionEl = document.getElementById("billboard-description");
  const backdropEl = document.getElementById("billboard-backdrop");
  const playButton = document.getElementById("billboard-play");
  const randomButton = document.getElementById("billboard-random");
  if (!titleEl || !descriptionEl || !backdropEl) {
    return;
  }

  const video = data.recommendations[0] || data.continueWatching[0] || null;
  activeVideo = video;
  if (!video) {
    titleEl.textContent = "Your personal METFLIX";
    descriptionEl.textContent = "Browse your media library, keep progress in cookies, and jump back in instantly.";
    backdropEl.style.background =
      "radial-gradient(circle at 65% 35%, rgba(255,255,255,0.14), transparent 16%), linear-gradient(180deg, rgba(229,9,20,0.14), transparent 45%)";
    return;
  }

  titleEl.textContent = truncateTitle(displayTitle(video), 32);
  titleEl.title = displayTitle(video);
  descriptionEl.textContent = `Featured from ${prettyLabel(video.main_category)}${video.subcategory ? ` / ${prettyLabel(video.subcategory)}` : ""}.`;
  backdropEl.style.background =
    "radial-gradient(circle at 72% 28%, rgba(255,255,255,0.18), transparent 14%), linear-gradient(180deg, rgba(229,9,20,0.24), transparent 42%)";
  if (playButton) {
    playButton.onclick = () => openPlayer(video);
  }
  if (randomButton) {
    randomButton.onclick = () => playRandomVideo();
  }
}

function renderHome(data) {
  renderBillboard(data);
  renderRail(continueWatchingEl, data.continueWatching, "Start a video and it will appear here so you can resume it later.");
  renderRail(document.getElementById("recommended-list"), data.recommendations, "No recommendations available yet.");
  renderCategories(data);
}

function renderCategories(data) {
  const root = document.getElementById("categories-root");
  if (!root) {
    return;
  }
  root.innerHTML = "";
  if (!data.main_categories.length) {
    root.innerHTML = '<section class="category-block"><div class="empty-state">Create folders like <code>Horror/Children</code> and <code>Horror/13+</code> under <code>/storage/emulated/0/Videos</code>.</div></section>';
    return;
  }

  data.main_categories.forEach((mainCategory) => {
    const section = document.createElement("section");
    section.className = "category-block";
    section.innerHTML = `
      <div class="category-block__header">
        <div>
          <h2>${prettyLabel(mainCategory.name)}</h2>
          <p>Random picks from all subcategories in this main category.</p>
        </div>
        <p>${pluralize(mainCategory.video_count || 0, "video")}</p>
      </div>
      <div class="rail category-block__featured"></div>
      <div class="subcategory-stack"></div>
    `;
    renderRail(section.querySelector(".category-block__featured"), mainCategory.featured_videos || [], "No videos in this main category.");

    const stack = section.querySelector(".subcategory-stack");
    mainCategory.subcategories.forEach((subcategory) => {
      const sub = document.createElement("section");
      sub.className = "subcategory-block";
      sub.innerHTML = `
        <div class="subcategory-block__header">
          <h3>${prettyLabel(subcategory.name)}</h3>
          <p>${pluralize(subcategory.video_count || 0, "video")}</p>
        </div>
        <div class="rail"></div>
      `;
      renderRail(sub.querySelector(".rail"), subcategory.videos || [], "No videos in this subcategory.");
      stack.appendChild(sub);
    });

    root.appendChild(section);
  });
}

function renderHistoryPage(data) {
  renderRail(continueWatchingEl, data.continueWatching, "Start a video and it will appear here so you can resume it later.");
  const historyVideos = [...data.all_videos]
    .filter((video) => historyFor(video.id))
    .sort((a, b) => (historyFor(b.id)?.updated_at || 0) - (historyFor(a.id)?.updated_at || 0));
  renderRail(document.getElementById("history-list"), historyVideos, "No watch history has been stored in cookies yet.");
}

function renderManageWatchedPage(data) {
  if (!manageWatchedListEl) {
    return;
  }
  manageWatchedListEl.innerHTML = "";
  const watchedVideos = [...data.all_videos]
    .filter((video) => historyFor(video.id)?.watched)
    .sort((a, b) => (historyFor(b.id)?.updated_at || 0) - (historyFor(a.id)?.updated_at || 0));

  if (!watchedVideos.length) {
    manageWatchedListEl.innerHTML = '<div class="empty-state">No watched videos are stored in cookies yet.</div>';
    return;
  }

  watchedVideos.forEach((video) => {
    const row = document.createElement("article");
    row.className = "manage-row";
    row.innerHTML =
      '<div class="manage-row__meta"><h3></h3><p></p></div>' +
      '<div class="manage-row__actions">' +
      '<button class="action-pill action-pill--light" type="button">Play</button>' +
      '<button class="action-pill" type="button">Remove</button>' +
      '<button class="action-pill" type="button">Delete File</button>' +
      '</div>';
    row.querySelector("h3").textContent = displayTitle(video);
    row.querySelector("p").textContent = `${buildBadgeLabel(video)} | ${Math.round((video.progress || 1) * 100)}% watched`;
    const [playButton, removeButton, deleteButton] = row.querySelectorAll("button");
    playButton.addEventListener("click", () => openPlayer(video));
    removeButton.addEventListener("click", async () => {
      removeHistoryItem(video.id);
      await refreshLibrary();
    });
    deleteButton.addEventListener("click", async () => {
      await deleteVideo(video.id);
    });
    manageWatchedListEl.appendChild(row);
  });
}

async function refreshLibrary() {
  if (!isUnlocked) {
    return;
  }
  try {
    const raw = await fetchJSON("/api/library");
    if (!raw.hosting_enabled || raw.backend_connection?.connected === false) {
      clearRuntimeCaches();
    }
    library = enhanceVideos(raw);
    setSummary(library);
    renderInfo(library);
    renderShuffleControls(library);
    if (page === "home") {
      renderHome(library);
    } else if (page === "history") {
      renderHistoryPage(library);
    } else if (page === "manage-watched") {
      renderManageWatchedPage(library);
    }
  } catch (error) {
    clearRuntimeCaches();
    if (infoGridEl) {
      infoGridEl.innerHTML = "";
      infoGridEl.appendChild(createInfoCard("Library error", error.message));
    }
  }
}

function scheduleProgressSave() {
  if (!activeVideo || !videoPlayer || !videoPlayer.duration) {
    return;
  }
  window.clearTimeout(progressSaveTimer);
  progressSaveTimer = window.setTimeout(() => {
    const duration = Number.isFinite(videoPlayer.duration) ? videoPlayer.duration : 0;
    const position = Number.isFinite(videoPlayer.currentTime) ? videoPlayer.currentTime : 0;
    const progress = duration > 0 ? position / duration : 0;
    updateHistory(activeVideo, {
      duration,
      position,
      watched: progress >= 0.9,
      watch_count: Math.max(getWatchCount(activeVideo), progress >= 0.9 ? 1 : getWatchCount(activeVideo)),
    });
  }, 250);
}

async function openPlayer(video) {
  if (!library?.hosting_enabled || !library?.backend_connection?.connected || !modalEl) {
    return;
  }
  cancelAutoDelete();
  activeVideo = video;
  playerTitle.textContent = displayTitle(video);
  playerCategory.textContent = buildBadgeLabel(video);
  resetDeleteStatus(autoDeleteEnabled() ? "Auto-delete is armed when you close this player." : "");
  videoPlayer.src = video.url;
  modalEl.classList.remove("hidden");
  modalEl.setAttribute("aria-hidden", "false");

  const history = historyFor(video.id);
  const resumeTime = history?.position || 0;
  videoPlayer.onloadedmetadata = () => {
    if (resumeTime > 0 && resumeTime < videoPlayer.duration - 5) {
      videoPlayer.currentTime = resumeTime;
    }
  };

  try {
    await videoPlayer.play();
  } catch {
    // Autoplay may be blocked by the browser.
  }
}

function closePlayer() {
  if (!modalEl || modalEl.classList.contains("hidden")) {
    return;
  }
  const closingVideo = activeVideo;
  scheduleProgressSave();
  modalEl.classList.add("hidden");
  modalEl.setAttribute("aria-hidden", "true");
  videoPlayer.pause();
  videoPlayer.removeAttribute("src");
  videoPlayer.load();
  if (closingVideo) {
    scheduleAutoDelete(closingVideo);
  }
}

async function playRandomVideo() {
  if (!isUnlocked || !library?.all_videos?.length) {
    return;
  }
  const pool = library.all_videos.filter((video) => selectedShuffleKeys.has(video.shuffle_key));
  if (!pool.length) {
    if (shuffleSummaryEl) {
      shuffleSummaryEl.textContent = "Select at least one subcategory for shuffle.";
    }
    return;
  }
  pool.sort((a, b) => Number(a.watched) - Number(b.watched) || Math.random() - 0.5);
  await openPlayer(pool[0]);
}

async function unlockWithPassword(password) {
  await fetchJSON("/api/login", {
    method: "POST",
    body: JSON.stringify({ password }),
  });
  isUnlocked = true;
  if (gateOverlay) {
    gateOverlay.classList.add("hidden");
    gateOverlay.setAttribute("aria-hidden", "true");
  }
  await refreshLibrary();
}

async function lockSession() {
  await fetchJSON("/api/logout", { method: "POST", body: "{}" });
  clearRuntimeCaches();
  isUnlocked = false;
  if (gateOverlay) {
    gateOverlay.classList.remove("hidden");
    gateOverlay.setAttribute("aria-hidden", "false");
    showGateScreen(profileScreen);
  }
}

function wireCommonUI() {
  if (randomPlayButton) {
    randomPlayButton.addEventListener("click", playRandomVideo);
  }
  if (hostToggleButton) {
    hostToggleButton.addEventListener("click", async () => {
      await fetchJSON("/api/host/toggle", { method: "POST", body: "{}" });
      await refreshLibrary();
    });
  }
  if (autoDeleteToggle) {
    autoDeleteToggle.checked = autoDeleteEnabled();
    autoDeleteToggle.addEventListener("change", () => {
      setAutoDeleteEnabled(autoDeleteToggle.checked);
      if (!autoDeleteToggle.checked) {
        cancelAutoDelete();
        resetDeleteStatus("");
      } else if (activeVideo && modalEl && !modalEl.classList.contains("hidden")) {
        resetDeleteStatus("Auto-delete is armed when you close this player.");
      }
    });
  }
  if (shuffleSelectAllButton) {
    shuffleSelectAllButton.addEventListener("click", () => {
      if (!library) {
        return;
      }
      shuffleSelectionInitialized = true;
      collectShuffleOptions(library).forEach((option) => selectedShuffleKeys.add(option.key));
      renderShuffleControls(library);
    });
  }
  if (shuffleClearAllButton) {
    shuffleClearAllButton.addEventListener("click", () => {
      shuffleSelectionInitialized = true;
      selectedShuffleKeys.clear();
      if (library) {
        renderShuffleControls(library);
      }
    });
  }
  if (logoutButton) {
    logoutButton.addEventListener("click", lockSession);
  }
  if (closePlayerButton) {
    closePlayerButton.addEventListener("click", closePlayer);
  }
  if (modalEl) {
    modalEl.querySelector(".player-modal__backdrop").addEventListener("click", closePlayer);
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closePlayer();
    }
  });
  if (videoPlayer) {
    videoPlayer.addEventListener("timeupdate", scheduleProgressSave);
    videoPlayer.addEventListener("pause", scheduleProgressSave);
    videoPlayer.addEventListener("ended", async () => {
      if (!activeVideo) {
        return;
      }
      updateHistory(activeVideo, {
        duration: Number.isFinite(videoPlayer.duration) ? videoPlayer.duration : 0,
        position: Number.isFinite(videoPlayer.duration) ? videoPlayer.duration : 0,
        watched: true,
        watch_count: getWatchCount(activeVideo) + 1,
      });
      await refreshLibrary();
    });
  }
  if (deleteVideoButton) {
    deleteVideoButton.addEventListener("click", async () => {
      if (!activeVideo) {
        return;
      }
      try {
        resetDeleteStatus("Deleting video...");
        await deleteVideo(activeVideo.id);
      } catch (error) {
        resetDeleteStatus(error.message);
      }
    });
  }
  if (profileButton) {
    profileButton.addEventListener("click", () => {
      passwordError.textContent = "";
      showGateScreen(passwordScreen);
      passwordInput.focus();
    });
  }
  if (backToProfileButton) {
    backToProfileButton.addEventListener("click", () => {
      passwordError.textContent = "";
      showGateScreen(profileScreen);
    });
  }
  if (passwordForm) {
    passwordForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await unlockWithPassword(passwordInput.value);
        passwordInput.value = "";
      } catch (error) {
        passwordError.textContent = error.message;
      }
    });
  }
  if (clearWatchedButton) {
    clearWatchedButton.addEventListener("click", async () => {
      clearWatchedHistory();
      await refreshLibrary();
    });
  }
}

async function init() {
  wireCommonUI();
  await startGateFlow();
  if (isUnlocked) {
    await refreshLibrary();
  }
}

init();

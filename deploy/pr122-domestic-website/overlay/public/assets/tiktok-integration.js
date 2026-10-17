(function () {
  var statusText = document.querySelector("[data-tiktok-status]");
  var accountPanel = document.querySelector("[data-tiktok-account]");
  var displayName = document.querySelector("[data-tiktok-display-name]");
  var openId = document.querySelector("[data-tiktok-open-id]");
  var scope = document.querySelector("[data-tiktok-scope]");
  var disconnect = document.querySelector("[data-tiktok-disconnect]");

  if (!statusText || !accountPanel || !disconnect) {
    return;
  }

  function clearAccount() {
    accountPanel.hidden = true;
    disconnect.disabled = true;
    if (displayName) { displayName.textContent = ""; }
    if (openId) { openId.textContent = ""; }
    if (scope) { scope.textContent = ""; }
  }

  function setDisconnected(message) {
    clearAccount();
    statusText.textContent = message || "未连接 TikTok";
  }

  function setUnknown(message) {
    clearAccount();
    statusText.textContent = message || "TikTok 连接状态未知，请稍后重试";
  }

  setUnknown("正在检查 TikTok 连接状态");
  fetch("/integrations/tiktok/status?ts=" + Date.now(), {
    credentials: "same-origin",
    cache: "no-store"
  })
    .then(function (response) {
      if (!response.ok) {
        throw new Error("TIKTOK_STATUS_HTTP_" + response.status);
      }
      return response.json();
    })
    .then(function (payload) {
      if (!payload || payload.connected !== true || !payload.account) {
        setDisconnected("未连接 TikTok");
        return;
      }
      statusText.textContent = "已连接 TikTok 账号";
      accountPanel.hidden = false;
      disconnect.disabled = false;
      if (displayName) { displayName.textContent = payload.account.display_name || "已连接 TikTok 账号"; }
      if (openId) { openId.textContent = payload.account.open_id_masked || "已连接"; }
      if (scope) { scope.textContent = payload.scope || "user.info.basic"; }
    })
    .catch(function () {
      setUnknown();
    });

  disconnect.addEventListener("click", function () {
    disconnect.disabled = true;
    fetch("/integrations/tiktok/disconnect", {
      method: "POST",
      credentials: "same-origin"
    }).then(function (response) {
      if (!response.ok) {
        throw new Error("TIKTOK_DISCONNECT_HTTP_" + response.status);
      }
      setDisconnected("已断开连接");
    }).catch(function () {
      setUnknown("断开结果未知，请刷新后确认");
    });
  });
}());

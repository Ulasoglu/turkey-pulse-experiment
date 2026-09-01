(() => {
  closeMobileSheet = function closeMobileFeedAndResetProvince(reset = true) {
    mobileSheet.classList.remove("open");
    setBottomActive("mobileMap");

    if (reset && selectedProvince) {
      resetToTurkey();
    }
  };
})();

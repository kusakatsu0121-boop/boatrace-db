export const LISTING_STATUS = Object.freeze({
  VERIFIED_ACTIVE: 'verified_active',
  VERIFIED_ACTIVE_VIA_LIST: 'verified_active_via_list',
  RECHECK_NEEDED: 'recheck_needed',
  ENDED: 'ended',
});

export function normalizeListingStatus(evidence = {}) {
  const {
    directPageVisible = false,
    currentListVisible = false,
    explicitEnded = false,
    searchVisible = false,
  } = evidence;

  // End only when the source explicitly says the job is closed/removed.
  // A missing search result is never enough to mark a listing ended.
  if (explicitEnded) return LISTING_STATUS.ENDED;
  if (directPageVisible) return LISTING_STATUS.VERIFIED_ACTIVE;
  if (currentListVisible) return LISTING_STATUS.VERIFIED_ACTIVE_VIA_LIST;

  // Search visibility is weak evidence. Keep it for review, not for deletion.
  if (searchVisible) return LISTING_STATUS.RECHECK_NEEDED;
  return LISTING_STATUS.RECHECK_NEEDED;
}

export function isEligibleForComparison(status) {
  return status !== LISTING_STATUS.ENDED;
}

export function shouldShowFreshnessWarning(status) {
  return status === LISTING_STATUS.RECHECK_NEEDED;
}

export function listingStatusLabel(status) {
  switch (status) {
    case LISTING_STATUS.VERIFIED_ACTIVE:
      return '掲載確認済み';
    case LISTING_STATUS.VERIFIED_ACTIVE_VIA_LIST:
      return '一覧で掲載確認';
    case LISTING_STATUS.ENDED:
      return '掲載終了';
    default:
      return '要再確認';
  }
}

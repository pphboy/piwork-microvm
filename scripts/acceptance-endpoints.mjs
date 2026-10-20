// Test-only endpoint selection: browser traffic and CLI/backend traffic use
// the same two independent listeners as the unmodified upstream application.
export const coreOrigin = new URL('http://127.0.0.1:' + Number(process.env.PIWORK_ACCEPTANCE_CORE_PORT || 17871)).origin;

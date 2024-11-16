async function timeout(promise, ms, errorMsg) {
  let timer;
  const timeoutPromise = new Promise((_, reject) => {
    timer = setTimeout(
      () => reject(new Error(!errorMsg ? "Timeout" : errorMsg)),
      ms
    );
  });
  return Promise.race([promise, timeoutPromise]).finally(() =>
    clearTimeout(timer)
  );
}

export default timeout;

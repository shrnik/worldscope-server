async function timeout<T>(
  promise: Promise<T>,
  ms: number,
  errorMsg?: string
): Promise<T> {
  let timer: Timer;
  const timeoutPromise = new Promise<any>((_, reject) => {
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

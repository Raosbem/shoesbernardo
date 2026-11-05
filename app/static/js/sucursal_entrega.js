(() => {
  const form = document.getElementById('precios-form');
  const credit = document.getElementById('vale');
  const currency = new Intl.NumberFormat('es-MX', {style: 'currency', currency: 'MXN'});
  const round = value => Math.round((value + Number.EPSILON) * 100) / 100;
  let gross = 0;
  function calculate() {
    let subtotal = 0, commission = 0;
    form.querySelectorAll('.articulo-precio').forEach(row => {
      const price = Number(row.querySelector('.precio').value);
      const discount = Number(row.querySelector('.descuento').value);
      const net = round(price * (1 - discount / 100));
      if (Number.isFinite(net) && net >= 0) {
        subtotal = round(subtotal + net);
        row.querySelector('.neto').textContent = currency.format(net);
      }
    });
    commission = round(subtotal * Number(form.dataset.comision) / 100);
    gross = round(subtotal + commission);
    const used = Number(credit.value) || 0;
    credit.setCustomValidity(used > gross ? 'El vale aplicado no puede superar el total de esta entrega.' : '');
    document.getElementById('subtotal').textContent = currency.format(subtotal);
    document.getElementById('comision').textContent = currency.format(commission);
    document.getElementById('credito').textContent = currency.format(used);
    document.getElementById('total').textContent = currency.format(round(gross - used));
  }
  form.addEventListener('input', calculate);
  document.getElementById('usar-vales')?.addEventListener('click', event => {
    credit.value = Math.min(gross, Number(event.currentTarget.dataset.disponible)).toFixed(2);
    calculate();
  });
  calculate();
})();

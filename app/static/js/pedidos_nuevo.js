(() => {
  'use strict';
  const form = document.getElementById('pedido-form');
  const branchMode = form.dataset.modo === 'sucursal';
  const editor = document.getElementById('editor');
  const fields = [...editor.querySelectorAll('[data-campo]')];
  const list = document.getElementById('lista-articulos');
  const add = document.getElementById('otro-articulo');
  const save = document.getElementById('guardar-articulo');
  const discard = document.getElementById('cancelar-edicion');
  const submit = document.getElementById('registrar');
  const notice = document.getElementById('aviso');
  const shop = document.getElementById('zapateria');
  const currency = new Intl.NumberFormat('es-MX', {style: 'currency', currency: 'MXN'});
  let articles = JSON.parse(document.getElementById('articulos-iniciales').textContent);
  let editing = null;
  let submitting = false;

  const draft = () => Object.fromEntries(fields.map(field => [field.dataset.campo, field.value.trim()]));
  const hasDraft = () => !editor.hidden && fields.some(field => field.value.trim() !== '');
  const label = count => `${branchMode ? 'Enviar' : 'Registrar'} ${count} artículo${count === 1 ? '' : 's'}`;
  const warn = message => { notice.textContent = message; notice.hidden = false; };
  const hideNotice = () => { notice.hidden = true; };

  function showEditor(index = null) {
    if (hasDraft() && !window.confirm('¿Descartar los cambios del artículo que estás capturando?')) return;
    editing = index;
    fields.forEach(field => { field.value = index === null ? '' : (articles[index][field.dataset.campo] || ''); });
    editor.hidden = false;
    add.hidden = true;
    discard.hidden = articles.length === 0;
    document.getElementById('editor-titulo').textContent = index === null ? 'Nuevo artículo' : `Editar artículo ${index + 1}`;
    save.textContent = index === null ? 'Agregar al pedido' : 'Guardar artículo';
    hideNotice();
    render();
    document.getElementById('editor-titulo').focus();
    editor.scrollIntoView({behavior: 'smooth', block: 'start'});
  }

  function closeEditor() {
    editing = null;
    fields.forEach(field => { field.value = ''; });
    editor.hidden = true;
    add.hidden = false;
    render();
  }

  function storeDraft() {
    const code = document.getElementById('codigo');
    code.value = code.value.trim();
    for (const field of fields) {
      if (!field.reportValidity()) return false;
    }
    if (editing === null && articles.length >= 50) {
      warn('Puedes registrar hasta 50 artículos por vez. Guarda este pedido antes de agregar más.');
      return false;
    }
    if (editing === null) articles.push(draft());
    else articles[editing] = draft();
    hideNotice();
    closeEditor();
    return true;
  }

  function render() {
    list.replaceChildren();
    document.getElementById('resumen').hidden = articles.length === 0;
    let cents = 0;
    articles.forEach((article, index) => {
      const row = document.createElement('div');
      row.className = 'border-bottom py-3';
      if (editing === index) row.classList.add('bg-light');
      const heading = document.createElement('div');
      heading.className = 'fw-semibold';
      const option = [...shop.options].find(option => option.value === String(article.zapateria_id));
      heading.textContent = `${index + 1}. ${option?.textContent || 'Selecciona zapatería'} · ${article.codigo || 'Sin código'}`;
      const details = document.createElement('div');
      details.className = 'small text-muted my-1';
      details.textContent = [article.descripcion, article.talla ? `Talla ${article.talla}` : '', article.color].filter(Boolean).join(' · ');
      const price = document.createElement('div');
      const amount = Number(branchMode ? article.precio_referencia : article.precio_venta);
      price.textContent = branchMode ? (Number.isFinite(amount) && amount > 0 ? `Referencia: ${currency.format(amount)}` : 'Precio por confirmar al entregar') : (Number.isFinite(amount) && amount > 0 ? currency.format(amount) : 'Revisa el precio de venta');
      if (Number.isFinite(amount)) cents += Math.round(amount * 100);
      const actions = document.createElement('div');
      actions.className = 'd-flex gap-2 mt-2';
      const edit = document.createElement('button');
      edit.type = 'button'; edit.className = 'btn btn-outline-secondary btn-sm'; edit.textContent = 'Editar';
      edit.setAttribute('aria-label', `Editar artículo ${index + 1}`);
      edit.addEventListener('click', () => showEditor(index));
      const remove = document.createElement('button');
      remove.type = 'button'; remove.className = 'btn btn-outline-danger btn-sm'; remove.textContent = 'Quitar';
      remove.setAttribute('aria-label', `Quitar artículo ${index + 1}`);
      remove.addEventListener('click', () => {
        if (!window.confirm(`¿Quitar el artículo ${index + 1} del pedido?`)) return;
        articles.splice(index, 1);
        if (editing === index) closeEditor();
        else if (editing !== null && editing > index) editing -= 1;
        if (articles.length === 0 && editor.hidden) showEditor();
        render();
      });
      actions.append(edit, remove);
      row.append(heading, details, price, actions);
      list.append(row);
    });
    document.getElementById('total').textContent = `${articles.length} artículo${articles.length === 1 ? '' : 's'} · ${branchMode ? 'Importe final por confirmar' : currency.format(cents / 100)}`;
    const count = articles.length + (hasDraft() && editing === null ? 1 : 0);
    submit.textContent = label(Math.max(1, count));
  }

  save.addEventListener('click', () => {
    if (storeDraft()) add.focus();
  });
  add.addEventListener('click', () => showEditor());
  discard.addEventListener('click', () => {
    if (hasDraft() && !window.confirm('¿Descartar los cambios de este artículo?')) return;
    closeEditor(); hideNotice();
  });
  fields.forEach(field => field.addEventListener('input', render));
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (submitting) return;
    const customer = document.getElementById('cliente');
    if (customer && !customer.reportValidity()) return;
    if (hasDraft() && !storeDraft()) return;
    if (articles.length === 0) {
      warn('Agrega al menos un artículo para registrar el pedido.');
      fields.find(field => !field.checkValidity())?.reportValidity();
      return;
    }
    document.getElementById('articulos').value = JSON.stringify(articles);
    if (branchMode) document.getElementById('intencion').value = event.submitter?.value === 'borrador' ? 'borrador' : 'enviar';
    submitting = true;
    submit.disabled = true;
    submit.textContent = branchMode ? (document.getElementById('intencion').value === 'borrador' ? 'Guardando…' : 'Enviando…') : 'Registrando…';
    form.submit();
  });
  window.addEventListener('beforeunload', event => {
    if (!submitting && (articles.length > 0 || hasDraft())) {
      event.preventDefault(); event.returnValue = '';
    }
  });
  window.addEventListener('pageshow', () => { submitting = false; submit.disabled = false; render(); });
  if (articles.length) closeEditor();
  render();
  submit.disabled = false;
})();

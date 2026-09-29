// --- PEGA AQUÍ EL ID DE TU GOOGLE SHEET ---
var SPREADSHEET_ID = "11GeK3nreRimIGO3Jtc4fbsW65p48B2ckkhC1yXOuxlg";

function normalizarTexto(texto) {
  if (!texto) return "";
  return texto
    .toString()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, "");
}

function crearRespuestaJSON(objeto) {
  return ContentService
    .createTextOutput(JSON.stringify(objeto))
    .setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  // 1. Obtener bloqueo exclusivo de script (espera hasta 10 segundos a que finalice la petición anterior)
  var lock = LockService.getScriptLock();
  try {
    var success = lock.tryLock(10000); // Espera máximo 10s si otra petición está escribiendo
    if (!success) {
      return crearRespuestaJSON({
        status: "error",
        message: "El sistema está ocupado. Intenta de nuevo en unos segundos."
      });
    }

    if (!e || !e.postData || !e.postData.contents) {
      return crearRespuestaJSON({ status: "error", message: "Cuerpo de solicitud vacío" });
    }

    var data = JSON.parse(e.postData.contents);
    var accion = data.accion;
    var nombreBuscado = data.nombre || "";
    var monto = Number(data.monto) || 0;

    // Conexión directa por ID (mucho más rápida y estable que getActiveSpreadsheet)
    var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
    var sheetDeudores = ss.getSheetByName("Deudores") || ss.getSheets()[0];
    var sheetAbonos = ss.getSheetByName("Abonos");

    if (!sheetAbonos) {
      sheetAbonos = ss.insertSheet("Abonos");
      sheetAbonos.appendRow(["Fecha", "Nombre", "Monto"]);
    }

    var nombreBuscadoNorm = normalizarTexto(nombreBuscado);

    // --- BÚSQUEDA DEL DEUDOR EN LA TABLA ---
    var lastRowDeudores = sheetDeudores.getLastRow();
    var datosDeudores = lastRowDeudores > 1 ? sheetDeudores.getRange(2, 1, lastRowDeudores - 1, 2).getValues() : [];
    
    var nombreReal = "";
    var deudaInicial = 0;
    var existeDeudor = false;

    for (var i = 0; i < datosDeudores.length; i++) {
      if (normalizarTexto(datosDeudores[i][0]) === nombreBuscadoNorm) {
        nombreReal = datosDeudores[i][0];
        deudaInicial = Number(datosDeudores[i][1]) || 0;
        existeDeudor = true;
        break;
      }
    }

    // --- 1. ACCIÓN: AGREGAR NUEVO DEUDOR ---
    if (accion === "nuevo") {
      if (existeDeudor) {
        return crearRespuestaJSON({ status: "error", message: "El deudor ya existe" });
      }

      sheetDeudores.appendRow([nombreBuscado, monto]);
      SpreadsheetApp.flush(); // Forzar la escritura mientras mantenemos el Lock

      return crearRespuestaJSON({ status: "ok" });
    }

    // Si la acción requiere que el deudor exista y no está:
    if (!existeDeudor) {
      return crearRespuestaJSON({ status: "error", message: "Deudor no encontrado" });
    }

    // --- 2. ACCIÓN: REGISTRAR ABONO ---
    if (accion === "abono") {
      var fechaHoy = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "dd/MM/yyyy HH:mm");
      sheetAbonos.appendRow([fechaHoy, nombreReal, monto]);
      SpreadsheetApp.flush();

      var totalAbonos = obtenerTotalAbonado(sheetAbonos, nombreBuscadoNorm);
      var saldoPendiente = deudaInicial - totalAbonos;

      return crearRespuestaJSON({
        status: "ok",
        nombre: nombreReal,
        saldo: saldoPendiente
      });
    }

    // --- 3. ACCIÓN: CONSULTAR SALDO E HISTORIAL ---
    if (accion === "saldo") {
      var lastRowAbonos = sheetAbonos.getLastRow();
      var datosAbonos = lastRowAbonos > 1 ? sheetAbonos.getRange(2, 1, lastRowAbonos - 1, 3).getValues() : [];

      var historial = [];
      var totalAbonos = 0;

      for (var j = 0; j < datosAbonos.length; j++) {
        var fechaAbono = datosAbonos[j][0];
        var nombreAbono = datosAbonos[j][1];
        var montoAbono = Number(datosAbonos[j][2]) || 0;

        if (normalizarTexto(nombreAbono) === nombreBuscadoNorm) {
          totalAbonos += montoAbono;
          
          var fechaTexto = (fechaAbono instanceof Date) 
            ? Utilities.formatDate(fechaAbono, Session.getScriptTimeZone(), "dd/MM/yyyy") 
            : fechaAbono;

          historial.push({ fecha: fechaTexto, monto: montoAbono });
        }
      }

      return crearRespuestaJSON({
        status: "ok",
        nombre: nombreReal,
        deuda: deudaInicial,
        abonos: totalAbonos,
        saldo: deudaInicial - totalAbonos,
        historial: historial
      });
    }

    return crearRespuestaJSON({ status: "error", message: "Acción no reconocida" });

  } catch (err) {
    return crearRespuestaJSON({ status: "error", message: err.toString() });
  } finally {
    // Liberar siempre el bloqueo al finalizar la solicitud
    lock.releaseLock();
  }
}

function obtenerTotalAbonado(sheetAbonos, nombreNorm) {
  var lastRow = sheetAbonos.getLastRow();
  if (lastRow <= 1) return 0;

  var datos = sheetAbonos.getRange(2, 1, lastRow - 1, 3).getValues();
  var total = 0;

  for (var i = 0; i < datos.length; i++) {
    if (normalizarTexto(datos[i][1]) === nombreNorm) {
      total += Number(datos[i][2]) || 0;
    }
  }
  return total;
}

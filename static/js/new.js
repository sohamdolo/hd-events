var roomAlert = function(self, msg) {
  var answer = confirm(msg);
  if (answer) {
    $(self)
      .attr('checked', true);
  } else {
    $(self)
      .removeAttr('checked');
  }
}

$(function() {
  $(".datepicker")
    .datepicker({
    minDate: 0
  });
  $("#start_date")
    .datepicker({
    minDate: 0,
    onSelect: function(dateText, inst) {
      if ($("#end_date")
        .val() == "") {
        $("#end_date")
          .val(dateText)
      }
    }
  });

  try {
    var formvalues = $.cookie('formvalues');
    if (formvalues) {
      formvalues = JSON.parse(formvalues);
      $('#type-select')
        .append('<option>' + formvalues['type'] + '</option>');
      for (var key in formvalues) {
        if (key != "rooms") {
          $('[name=' + key + ']')
            .val(formvalues[key]);
        }
      }
      $.each($('[name=rooms]'), function(key, value) {
        if ($(value)
          .val() == formvalues["rooms"]) {
          $(value)
            .attr("checked", "checked");
        }
      });
    }
    var formerror = $.cookie('formerror');
    if (formerror) {
      formerror = JSON.parse(formerror);
      $('#warn')
        .hide();
      $('#error')
        .show("slow")
        .append("<b>Error:</b> " + formerror);
      $.cookie('formerror', null);
    }
  } catch (err) {
    // noop
  }

  checkCanSubmit();

  $('#room-MakerSpace')
    .click(function() {
    roomAlert(this, "The Maker Space can only be reserved for events that need the tools available in that room. Please confirm your event meets this requirement.")
  });
  $('#room-Loungey')
    .click(function() {
    roomAlert(this, "Loungey can only be reserved for fun/social events.  Please confirm your event meets this requirement.")
  });
  $('#policies-agree').click(function() {
    checkCanSubmit();
  });
});

function showOther() {
  $('#type-select')
    .css('display', 'none');
  $('#type-text')
    .css('display', 'inline');
}

function hideOther() {
  $('#type-select')
    .css('display', 'inline');
  $('#type-text')
    .css('display', 'none');
}

/** Enables and disables the submit button based on whether or not the user has
 * checked the "I agree" box. */
function checkCanSubmit() {
  if (document.getElementById('policies-agree').checked) {
    // We agreed, enable the submit button.
    $('#submit').removeAttr('disabled');
    $('#submit').removeClass('disabled');
  } else {
    // We did not agree, disable the submit button.
    $('#submit').attr('disabled', 'disabled')
    $('#submit').addClass('disabled');
  }
};

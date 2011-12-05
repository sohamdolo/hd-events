$(function() {
  $(".datepicker").datepicker({minDate: 0});
  $("#start_date").datepicker({
      minDate: 0,
      onSelect: function(dateText, inst){
          if($("#end_date").val() == ""){
              $("#end_date").val(dateText)
          }
      }
  });

  try {
    var formvalues = $.cookie('formvalues');
    if (formvalues) {
      formvalues = JSON.parse(formvalues);
      $('#type-select').append('<option>'+formvalues['type']+'</option>');
      for (var key in formvalues) {
  if (key!="rooms") {
    $('[name='+key+']').val(formvalues[key]);
  }
      }
      $.each($('[name=rooms]'), function(key, value) {
  if ($(value).val()==formvalues["rooms"]) {
    $(value).attr("checked", "checked");
  }
      });
    }
    var formerror = $.cookie('formerror');
    if (formerror) {
      formerror = JSON.parse(formerror);
      $('#warn').hide();
      $('#error').show("slow").append("<b>Error:</b> "+ formerror);
      $.cookie('formerror', null);
    }
  } catch (err) {
    // noop
  }

});

function showOther() {
  $('#type-select').css('display','none');$('#type-text').css('display','inline');
}
function hideOther() {
  $('#type-select').css('display','inline');$('#type-text').css('display','none');
}
